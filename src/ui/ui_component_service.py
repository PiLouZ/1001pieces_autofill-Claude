"""
Service des composants UI - Phase 2.12
Extrait de main_refactored.py pour centraliser la logique de création et gestion des composants UI

Responsabilités:
- Création des boutons d'export avec styles et connexions
- Configuration des contrôles de pagination modernes
- Mise à jour de l'état des boutons selon le contexte de recherche
- Interface standardisée pour la gestion des composants UI dynamiques
"""

import time
import qtawesome as qta
from ..utils.qt_imports import (
    QVBoxLayout,
    QGridLayout,
    QPushButton,
    QToolButton,
    QSizePolicy,
    Qt,
    QTimer,
    QObject,
    QEvent,
    QCursor
)

from ..core.constants import ExportFormat
from .style_manager import StyleManager
from .menu_gabarits import MenuGabarits

class FlecheGabarits(QObject):
    """Flèche d'un bouton à gabarits : survol = menu des autres gabarits,
    clic = fenêtre d'aperçu d'export. Le reste du bouton garde son clic
    (export avec le gabarit par défaut).

    Menu ouvert au survol, le clic sur la flèche n'arrive à personne : macOS le
    consomme pour fermer le menu. On le reconnaît à la fermeture du menu :
    aucun gabarit choisi, pas d'Échap, souris sur la flèche → aperçu."""

    LARGEUR_FLECHE = 32   # zone ::menu-button des styles (30 px) + bordure
    DELAI_SURVOL_MS = 250
    ANTI_REBOND_S = 0.5   # 2e clic d'un double-clic : pas de 2e chargement

    def __init__(self, bouton, ouvrir_apercu):
        super().__init__(bouton)
        self._bouton = bouton
        self._ouvrir_apercu = ouvrir_apercu
        self._dernier_apercu = 0.0
        # Après l'aperçu, pas de menu tant que la souris n'a pas quitté la flèche
        self._attendre_sortie = False
        self._echap = False
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(self.DELAI_SURVOL_MS)
        self._minuterie.timeout.connect(self._ouvrir_menu)
        bouton.setAttribute(Qt.WA_Hover, True)
        bouton.installEventFilter(self)

    def _sur_fleche(self, pos) -> bool:
        return (self._bouton.popupMode() == QToolButton.MenuButtonPopup
                and pos.x() >= self._bouton.width() - self.LARGEUR_FLECHE)

    def _curseur_sur_fleche(self) -> bool:
        pos = self._bouton.mapFromGlobal(QCursor.pos())
        return self._bouton.rect().contains(pos) and self._sur_fleche(pos)

    def _apercu(self):
        self._minuterie.stop()
        self._attendre_sortie = True
        if time.monotonic() - self._dernier_apercu < self.ANTI_REBOND_S:
            return
        self._dernier_apercu = time.monotonic()
        self._ouvrir_apercu()

    def _ouvrir_menu(self):
        menu = self._bouton.menu()
        if (menu is None or not self._bouton.isEnabled() or not self._bouton.underMouse()
                or not self._curseur_sur_fleche()):
            return
        # Rien d'autre que le gabarit par défaut : pas de menu vide
        if not [a for a in menu.actions() if a.data()]:
            return
        choix = []
        self._echap = False
        menu.installEventFilter(self)   # Échap
        menu.triggered.connect(choix.append)
        try:
            self._bouton.showMenu()     # bloquant jusqu'à la fermeture du menu
        finally:
            menu.triggered.disconnect(choix.append)
            menu.removeEventFilter(self)
        if not choix and not self._echap and self._curseur_sur_fleche():
            # Après la sortie de la boucle du menu
            QTimer.singleShot(0, self._apercu)

    def eventFilter(self, objet, evenement):
        type_ = evenement.type()
        if objet is not self._bouton:
            if type_ == QEvent.KeyPress and evenement.key() == Qt.Key_Escape:
                self._echap = True
            return super().eventFilter(objet, evenement)
        if type_ in (QEvent.HoverEnter, QEvent.HoverMove):
            if not self._sur_fleche(evenement.pos()):
                self._attendre_sortie = False
                self._minuterie.stop()
            elif not self._attendre_sortie and not self._minuterie.isActive():
                self._minuterie.start()
        elif type_ == QEvent.HoverLeave:
            self._attendre_sortie = False
            self._minuterie.stop()
        elif (type_ in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick)
              and evenement.button() == Qt.LeftButton and self._sur_fleche(evenement.pos())):
            self._apercu()
            return True
        elif (type_ == QEvent.MouseButtonRelease and evenement.button() == Qt.LeftButton
              and self._sur_fleche(evenement.pos())):
            return True
        return super().eventFilter(objet, evenement)


class UIComponentService:
    """
    Service spécialisé pour la création et gestion des composants UI
    
    Responsabilités:
    - Création des boutons d'export avec styles cohérents
    - Configuration des contrôles de pagination avec indicateurs
    - Gestion des états des boutons selon le contexte utilisateur
    - Styles et apparence unifiés pour tous les composants UI
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        self._apercus = {}   # genre → fenêtre d'aperçu d'export ouverte
        
    def add_export_buttons(self, layout: QVBoxLayout) -> None:
        """
        Ajouter les boutons d'export avec styles et connexions
        
        Args:
            layout: Layout parent où ajouter les boutons
        """
        # Disposition : voir la grille en fin de méthode.

        # Bouton Export CSV (fin de ligne 1)
        self.main_window.export_csv_btn = QPushButton("Exporter CSV")
        self.main_window.export_csv_btn.clicked.connect(
            lambda: self.main_window._export_data(ExportFormat.CSV)
        )
        self.main_window.export_csv_btn.setEnabled(False)
        self.main_window.export_csv_btn.setStyleSheet(
            StyleManager.bouton_export_plein(*StyleManager.COULEURS_EXPORT_CSV))
        
        # Bouton HTML Marques
        self.main_window.export_html_brands_btn = QPushButton("HTML Marques")
        self.main_window.export_html_brands_btn.clicked.connect(
            lambda: self.main_window._export_data(ExportFormat.HTML_BRANDS)
        )
        self.main_window.export_html_brands_btn.setEnabled(False)
        self.main_window.export_html_brands_btn.setStyleSheet(StyleManager.BOUTON_EXPORT_NEUTRE)
        
        # Bouton HTML Détails — split button compact (clic = export profil par
        # défaut, flèche superposée = menu des autres profils configurés)
        self.main_window.export_html_details_btn = QToolButton()
        self.main_window.export_html_details_btn.setText("HTML Détails")
        self.main_window.export_html_details_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.main_window.export_html_details_btn.setStyleSheet(StyleManager.BOUTON_SPLIT_NEUTRE)
        self.main_window.export_html_details_btn.clicked.connect(
            self._on_export_html_details_clicked
        )
        self.main_window.export_html_details_btn.setToolTip(
            "Copier la liste des appareils groupés par marque\n"
            "Flèche : survol = autres profils, clic = aperçu")
        self.main_window.export_html_details_btn.setEnabled(False)
        # QToolButton a une politique de taille horizontale "Fixed" par défaut
        # (contrairement à QPushButton, "Preferred") : aligner sur "HTML Marques"
        # pour que les 3 boutons d'export gardent la même largeur/hauteur
        self.main_window.export_html_details_btn.setSizePolicy(
            self.main_window.export_html_brands_btn.sizePolicy()
        )
        self._refresh_html_details_menu()

        # Bouton Titre de fiche produit — split button comme "HTML Détails"
        # (clic = gabarit par défaut, flèche = autres gabarits configurés)
        self.main_window.titre_btn = QToolButton()
        self.main_window.titre_btn.setText("Titre")
        # Texte seul, comme "HTML Détails" : un QToolButton élargi aligne
        # icône + texte à gauche au lieu de les centrer
        self.main_window.titre_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.main_window.titre_btn.setStyleSheet(
            StyleManager.bouton_split_plein(*StyleManager.COULEURS_TITRE))
        self.main_window.titre_btn.setToolTip(
            "Copier le titre de la fiche produit : libellé, types, marques et référence la plus récente\n"
            "Flèche : survol = autres gabarits, clic = aperçu ; réglages dans la\n"
            "configuration des exports, onglet « Titre »")
        self.main_window.titre_btn.clicked.connect(self._on_titre_clicked)
        self.main_window.titre_btn.setEnabled(False)
        self.main_window.titre_btn.setSizePolicy(
            self.main_window.export_html_brands_btn.sizePolicy()
        )
        self._refresh_titre_menu()

        # Fiche complète — split button comme "Titre"
        self.main_window.fiche_btn = QToolButton()
        self.main_window.fiche_btn.setText("Fiche complète")
        self.main_window.fiche_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.main_window.fiche_btn.setStyleSheet(
            StyleManager.bouton_split_plein(*StyleManager.COULEURS_FICHE))
        self.main_window.fiche_btn.setToolTip(
            "Copier le code HTML complet de la fiche produit : titre, marques, code produit,\n"
            "références remplacées et équivalentes, appareils affichés dans le tableau\n"
            "Flèche : survol = autres variantes, clic = aperçu ; réglages dans la\n"
            "configuration des exports, onglet « Fiche »")
        self.main_window.fiche_btn.clicked.connect(self._on_fiche_clicked)
        self.main_window.fiche_btn.setEnabled(False)
        self._refresh_fiche_menu()

        # Flèches : survol = autres gabarits, clic = aperçu d'export
        for btn, genre in ((self.main_window.titre_btn, 'titre'),
                           (self.main_window.fiche_btn, 'fiche'),
                           (self.main_window.export_html_details_btn, 'html_details')):
            FlecheGabarits(btn, lambda g=genre: self.ouvrir_apercu(g))

        # Méta Title, Méta Desc (Exporter CSV existe déjà)
        self._creer_boutons_seo()

        # Fiche PrestaShop et Cogilog : raccourci du menu Données (src/ui/agora_fiche.py),
        # actif comme Titre après une recherche par pièce
        self.main_window.fiche_site_btn = QPushButton(
            qta.icon('fa5s.store', color='white'), "Fiche PrestaShop et Cogilog")
        self.main_window.fiche_site_btn.setStyleSheet(
            StyleManager.bouton_export_plein(*StyleManager.COULEURS_FICHE_SITE))
        self.main_window.fiche_site_btn.setToolTip(
            "Fiche de la pièce recherchée : créer sur PrestaShop et/ou ajouter aux fichiers\n"
            "d'import du jour (menu Données → Fiche PrestaShop et Cogilog)")
        self.main_window.fiche_site_btn.clicked.connect(
            lambda: self.main_window._open_fiche_site_agora())
        self.main_window.fiche_site_btn.setEnabled(False)

        # Grille de 6 colonnes égales :
        # ligne 1 : Fiche PrestaShop et Cogilog (deux tiers) | Exporter CSV (un tiers) ;
        # ligne 2 : « Autres exports » repliable, contenant
        # ligne 3 : Méta Title | Méta Desc ; ligne 4 : Titre | Fiche complète ;
        # ligne 5 : HTML Marques | HTML Détails.
        grille = QGridLayout()
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setHorizontalSpacing(6)
        grille.setVerticalSpacing(6)
        for col in range(6):
            grille.setColumnStretch(col, 1)
        mw = self.main_window
        for ligne, boutons in ((0, ((mw.fiche_site_btn, 4), (mw.export_csv_btn, 2))),
                               (2, ((mw.meta_title_btn, 3), (mw.meta_desc_btn, 3))),
                               (3, ((mw.titre_btn, 2), (mw.fiche_btn, 4))),
                               (4, ((mw.export_html_brands_btn, 3), (mw.export_html_details_btn, 3)))):
            col = 0
            for btn, largeur in boutons:
                # Largeur fixée par la grille, pas par le texte du bouton
                btn.setSizePolicy(QSizePolicy.Ignored, btn.sizePolicy().verticalPolicy())
                grille.addWidget(btn, ligne, col, 1, largeur)
                col += largeur

        self.main_window.exports_html_toggle = QToolButton()
        self.main_window.exports_html_toggle.setText("Autres exports")
        self.main_window.exports_html_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.main_window.exports_html_toggle.setCheckable(True)
        self.main_window.exports_html_toggle.setToolTip(
            "Afficher ou masquer Méta Title, Méta Desc, Titre, Fiche complète, HTML Marques et HTML Détails")
        self.main_window.exports_html_toggle.setStyleSheet(
            "QToolButton { border: none; background: transparent; color: #6c757d;"
            " font-size: 11px; padding: 0px 2px; }"
            "QToolButton:hover { color: #343a40; }")
        self.main_window.exports_html_toggle.toggled.connect(self._afficher_exports_html)
        grille.addWidget(self.main_window.exports_html_toggle, 1, 0, 1, 6, Qt.AlignLeft)
        layout.addLayout(grille)

        settings = getattr(self.main_window, 'settings', None)
        visible = str(settings.value(self.CLE_EXPORTS_HTML, "false")).lower() == "true" if settings else False
        self.main_window.exports_html_toggle.setChecked(visible)
        self._afficher_exports_html(visible)

    # Panneau « Autres exports » déplié ou non, mémorisé par poste (clé historique de
    # l'ancien repli « Exports HTML » : un poste qui l'avait déplié garde le panneau ouvert)
    CLE_EXPORTS_HTML = "exports/html_visible"

    def _afficher_exports_html(self, visible: bool) -> None:
        """Déplier / replier le panneau « Autres exports »."""
        mw = self.main_window
        mw.exports_html_toggle.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)
        for btn in (mw.meta_title_btn, mw.meta_desc_btn, mw.titre_btn, mw.fiche_btn,
                    mw.export_html_brands_btn, mw.export_html_details_btn):
            btn.setVisible(visible)
        settings = getattr(self.main_window, 'settings', None)
        if settings is not None:
            settings.setValue(self.CLE_EXPORTS_HTML, "true" if visible else "false")

    def ouvrir_apercu(self, genre: str) -> None:
        """Fenêtre d'aperçu d'export du bouton (une par bouton, ramenée devant si ouverte)."""
        from .apercu_export_dialog import ApercuExportDialog
        fenetre = self._apercus.get(genre)
        if fenetre is None or not fenetre.isVisible():
            fenetre = ApercuExportDialog(self.main_window, genre, parent=self.main_window)
            fenetre.setAttribute(Qt.WA_DeleteOnClose, True)
            fenetre.destroyed.connect(lambda *_, g=genre: self._apercus.pop(g, None))
            self._apercus[genre] = fenetre
            fenetre.show()
        else:
            fenetre.recharger(interactif=False)
        fenetre.raise_()
        fenetre.activateWindow()

    def refresh_profile_menus(self) -> None:
        """Menus des boutons à gabarits, après modification de la configuration."""
        self._refresh_html_details_menu()
        self._refresh_titre_menu()
        self._refresh_fiche_menu()

    def _refresh_split_menu(self, btn, names, default_name, slot, cle_recents) -> None:
        """Reconstruire le menu déroulant d'un split button à profils.

        Aucun profil : pas de flèche. Sinon la flèche (cf. FlecheGabarits) :
        survol = menu listant les profils AUTRES que celui par défaut (le clic
        principal utilise déjà ce dernier ; rien ne s'ouvre s'il n'y en a pas),
        triés par ordre alphanumérique naturel, avec filtre et récents au-delà
        de quelques gabarits (MenuGabarits, v3.99.4) ; clic = aperçu d'export.
        """
        if not names:
            btn.setMenu(None)
            btn.setPopupMode(QToolButton.DelayedPopup)
            return

        menu = MenuGabarits(btn, names, default_name,
                            lambda: getattr(self.main_window, 'settings', None), cle_recents)
        menu.triggered.connect(slot)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.MenuButtonPopup)

    def _refresh_html_details_menu(self) -> None:
        """Reconstruire le menu déroulant du bouton "HTML Détails"."""
        svc = getattr(self.main_window, 'export_config_service', None)
        names = svc.get_details_profile_names() if svc else []
        default_name = svc.get_default_details_profile_name() if svc else None
        self._refresh_split_menu(self.main_window.export_html_details_btn, names,
                                 default_name, self._on_html_details_profile_chosen,
                                 "exports/recents/html_details")

    def _refresh_titre_menu(self) -> None:
        """Reconstruire le menu déroulant du bouton "Titre"."""
        svc = getattr(self.main_window, 'export_config_service', None)
        names = svc.get_titre_profile_names() if svc else []
        default_name = svc.get_default_titre_profile_name() if svc else None
        self._refresh_split_menu(self.main_window.titre_btn, names,
                                 default_name, self._on_titre_profile_chosen,
                                 "exports/recents/titre")

    def _refresh_fiche_menu(self) -> None:
        """Reconstruire le menu déroulant du bouton "Fiche complète"."""
        svc = getattr(self.main_window, 'export_config_service', None)
        names = svc.get_fiche_profile_names() if svc else []
        default_name = svc.get_default_fiche_profile_name() if svc else None
        self._refresh_split_menu(self.main_window.fiche_btn, names,
                                 default_name, self._on_fiche_profile_chosen,
                                 "exports/recents/fiche")

    def _on_fiche_clicked(self) -> None:
        """Clic sur "Fiche complète" : variante par défaut."""
        self.main_window._generer_fiche()

    def _on_fiche_profile_chosen(self, action) -> None:
        """Fiche complète avec la variante choisie dans le menu déroulant."""
        self.main_window._generer_fiche(profile_name=action.data())

    def _on_titre_clicked(self) -> None:
        """Clic sur "Titre" : gabarit par défaut."""
        self.main_window._generer_titre()

    def _on_titre_profile_chosen(self, action) -> None:
        """Titre avec le gabarit choisi dans le menu déroulant."""
        self.main_window._generer_titre(profile_name=action.data())

    def _on_html_details_profile_chosen(self, action) -> None:
        """Export HTML Détails avec le profil choisi dans le menu déroulant."""
        self.main_window._export_data(ExportFormat.HTML_DETAILS, profile_name=action.data())

    def _on_export_html_details_clicked(self):
        """Clic sur le bouton principal "HTML Détails" : export immédiat avec
        le profil par défaut (ou l'unique profil configuré)."""
        svc = getattr(self.main_window, 'export_config_service', None)
        default_name = svc.get_default_details_profile_name() if svc else None
        self.main_window._export_data(ExportFormat.HTML_DETAILS, profile_name=default_name)

    def _creer_boutons_seo(self) -> None:
        """Créer les boutons SEO métadonnées (placés par add_export_buttons)"""
        # Bouton Méta Title
        self.main_window.meta_title_btn = QPushButton(qta.icon('fa5s.heading', color='#555555'), "Méta Title")
        self.main_window.meta_title_btn.clicked.connect(self.main_window._generate_meta_title)
        self.main_window.meta_title_btn.setEnabled(False)
        self.main_window.meta_title_btn.setToolTip("Générer un méta titre SEO optimisé (largeur affichée par Google sur ordinateur)\nMaj+clic : autre formulation")
        self.main_window.meta_title_btn.setStyleSheet(
            StyleManager.bouton_export_plein(*StyleManager.COULEURS_META_TITLE))
        
        # Bouton Méta Description
        self.main_window.meta_desc_btn = QPushButton(qta.icon('fa5s.align-left', color='#555555'), "Méta Desc")
        self.main_window.meta_desc_btn.clicked.connect(self.main_window._generate_meta_description)
        self.main_window.meta_desc_btn.setEnabled(False)
        self.main_window.meta_desc_btn.setToolTip("Générer une méta description SEO (largeur affichée par Google sur ordinateur)\nMaj+clic : autre formulation")
        self.main_window.meta_desc_btn.setStyleSheet(
            StyleManager.bouton_export_plein(*StyleManager.COULEURS_META_DESC))

    def update_export_buttons_state_by_search(self, is_piece_search: bool) -> None:
        """
        Mettre à jour l'état des boutons d'export selon le type de recherche
        
        Args:
            is_piece_search: True si c'est une recherche de référence de pièce
        """
        # Tous les boutons d'export nécessitent une référence de pièce
        if hasattr(self.main_window, 'export_csv_btn'):
            self.main_window.export_csv_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'fiche_site_btn'):
            self.main_window.fiche_site_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'export_html_brands_btn'):
            self.main_window.export_html_brands_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'export_html_details_btn'):
            self.main_window.export_html_details_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'copy_csv_btn'):
            self.main_window.copy_csv_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'copy_html_btn'):
            self.main_window.copy_html_btn.setEnabled(is_piece_search)
