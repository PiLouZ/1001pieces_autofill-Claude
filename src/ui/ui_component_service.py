"""
Service des composants UI - Phase 2.12
Extrait de main_refactored.py pour centraliser la logique de création et gestion des composants UI

Responsabilités:
- Création des boutons d'export avec styles et connexions
- Configuration des contrôles de pagination modernes
- Mise à jour de l'état des boutons selon le contexte de recherche
- Interface standardisée pour la gestion des composants UI dynamiques
"""

from typing import Optional, Dict, Any
import qtawesome as qta
from .qt_imports import (QVBoxLayout, QHBoxLayout, QPushButton, QToolButton, QWidget,
                             QLabel, QSpinBox, QComboBox, QFrame, QSizePolicy,
                             Qt, QTimer, QFont, QMenu, QPoint)

from ..core.constants import ExportFormat
from .style_manager import StyleManager, icon_png_path
from src.core.logger import app_logger

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
        
    def add_export_buttons(self, layout: QVBoxLayout) -> None:
        """
        Ajouter les boutons d'export avec styles et connexions
        
        Args:
            layout: Layout parent où ajouter les boutons
        """
        # Ligne 1 : HTML Marques, HTML Détails, Titre.
        # Ligne 2 : Méta Title, Méta Desc, Exporter CSV (v3.99.0).
        # Trois colonnes égales sur les deux lignes (stretch 1 partout).
        export_layout = QHBoxLayout()
        
        # Bouton Export CSV (placé en fin de ligne 2, cf. _add_seo_buttons)
        self.main_window.export_csv_btn = QPushButton("Exporter CSV")
        self.main_window.export_csv_btn.clicked.connect(
            lambda: self.main_window._export_data(ExportFormat.CSV)
        )
        self.main_window.export_csv_btn.setEnabled(False)
        self.main_window.export_csv_btn.setStyleSheet(self._get_csv_button_style())
        
        # Bouton HTML Marques
        self.main_window.export_html_brands_btn = QPushButton("HTML Marques")
        self.main_window.export_html_brands_btn.clicked.connect(
            lambda: self.main_window._export_data(ExportFormat.HTML_BRANDS)
        )
        self.main_window.export_html_brands_btn.setEnabled(False)
        # Gabarit explicite, aligné sur CSV / Méta (8 × 12 px) : le style global
        # des boutons est plus compact.
        self.main_window.export_html_brands_btn.setStyleSheet(
            "QPushButton { padding: 8px 12px; font-weight: 500; }"
            f"QPushButton:disabled {{ {StyleManager.EXPORT_BTN_DISABLED_RULES} }}"
        )
        export_layout.addWidget(self.main_window.export_html_brands_btn, 1)
        
        # Bouton HTML Détails — split button compact (clic = export profil par
        # défaut, flèche superposée = menu des autres profils configurés)
        self.main_window.export_html_details_btn = QToolButton()
        self.main_window.export_html_details_btn.setText("HTML Détails")
        self.main_window.export_html_details_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.main_window.export_html_details_btn.setStyleSheet(self._get_split_button_style())
        self.main_window.export_html_details_btn.clicked.connect(
            self._on_export_html_details_clicked
        )
        self.main_window.export_html_details_btn.setEnabled(False)
        # QToolButton a une politique de taille horizontale "Fixed" par défaut
        # (contrairement à QPushButton, "Preferred") : aligner sur "HTML Marques"
        # pour que les 3 boutons d'export gardent la même largeur/hauteur
        self.main_window.export_html_details_btn.setSizePolicy(
            self.main_window.export_html_brands_btn.sizePolicy()
        )
        export_layout.addWidget(self.main_window.export_html_details_btn, 1)
        self._refresh_html_details_menu()

        # Bouton Titre de fiche produit — split button comme "HTML Détails"
        # (clic = gabarit par défaut, flèche = autres gabarits configurés)
        self.main_window.titre_btn = QToolButton()
        self.main_window.titre_btn.setText("Titre")
        # Texte seul, comme "HTML Détails" : un QToolButton élargi aligne
        # icône + texte à gauche au lieu de les centrer
        self.main_window.titre_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.main_window.titre_btn.setStyleSheet(self._get_titre_button_style())
        self.main_window.titre_btn.setToolTip(
            "Copier le titre de la fiche produit : libellé, types, marques et référence la plus récente\n"
            "Gabarits réglables dans la configuration des exports, onglet « Titre »")
        self.main_window.titre_btn.clicked.connect(self._on_titre_clicked)
        self.main_window.titre_btn.setEnabled(False)
        self.main_window.titre_btn.setSizePolicy(
            self.main_window.export_html_brands_btn.sizePolicy()
        )
        export_layout.addWidget(self.main_window.titre_btn, 1)
        self._refresh_titre_menu()

        layout.addLayout(export_layout)

        # Ligne 2: Boutons SEO métadonnées, puis Exporter CSV
        self._add_seo_buttons(layout)

        # Colonnes de même largeur sur les deux lignes : sans politique
        # extensible, un QToolButton à menu (« Titre ») restait à sa largeur utile
        for btn in (self.main_window.export_html_brands_btn, self.main_window.export_html_details_btn,
                    self.main_window.titre_btn, self.main_window.meta_title_btn,
                    self.main_window.meta_desc_btn, self.main_window.export_csv_btn):
            btn.setSizePolicy(QSizePolicy.Expanding, btn.sizePolicy().verticalPolicy())

    def refresh_profile_menus(self) -> None:
        """Menus des boutons à gabarits, après modification de la configuration."""
        self._refresh_html_details_menu()
        self._refresh_titre_menu()

    @staticmethod
    def _refresh_split_menu(btn, names, default_name, slot) -> None:
        """Reconstruire le menu déroulant d'un split button à profils.

        Un seul profil configuré : pas de menu, pas de flèche — clic = action directe.
        Plusieurs profils : la flèche superposée ouvre un menu listant les profils
        AUTRES que celui par défaut (le clic principal utilise déjà ce dernier).
        """
        if len(names) <= 1:
            btn.setMenu(None)
            btn.setPopupMode(QToolButton.DelayedPopup)
            return

        menu = QMenu(btn)
        for name in names:
            if name == default_name:
                continue
            action = menu.addAction(name)
            action.setData(name)
        menu.triggered.connect(slot)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.MenuButtonPopup)

    def _refresh_html_details_menu(self) -> None:
        """Reconstruire le menu déroulant du bouton "HTML Détails"."""
        svc = getattr(self.main_window, 'export_config_service', None)
        names = svc.get_details_profile_names() if svc else []
        default_name = svc.get_default_details_profile_name() if svc else None
        self._refresh_split_menu(self.main_window.export_html_details_btn, names,
                                 default_name, self._on_html_details_profile_chosen)

    def _refresh_titre_menu(self) -> None:
        """Reconstruire le menu déroulant du bouton "Titre"."""
        svc = getattr(self.main_window, 'export_config_service', None)
        names = svc.get_titre_profile_names() if svc else []
        default_name = svc.get_default_titre_profile_name() if svc else None
        self._refresh_split_menu(self.main_window.titre_btn, names,
                                 default_name, self._on_titre_profile_chosen)

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

    def _get_titre_button_style(self) -> str:
        """Style du bouton split "Titre" : violet plein, comme les boutons colorés
        de la ligne des métas ; flèche de menu blanche (la noire par défaut ne se
        lit pas sur le violet)."""
        fleche = icon_png_path('fa5s.caret-down', 'white', 10)
        regle_fleche = f"image: url({fleche}); width: 10px; height: 10px;" if fleche else ""
        return f"""
            QToolButton {{
                background-color: #6f42c1;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
            }}
            QToolButton:hover {{
                background-color: #5e37a6;
            }}
            QToolButton:pressed {{
                background-color: #512f8f;
            }}
            QToolButton:disabled {{
                {StyleManager.EXPORT_BTN_DISABLED_RULES}
            }}
            QToolButton::menu-button {{
                border: none;
                border-left: 1px solid rgba(255, 255, 255, 0.35);
                width: 30px;
            }}
            QToolButton::menu-arrow {{
                {regle_fleche}
            }}
        """

    def _get_split_button_style(self) -> str:
        """Style du bouton split "HTML Détails" — aligné sur le QPushButton global."""
        return f"""
            QToolButton {{
                background: white;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                color: #343a40;
            }}
            QToolButton:hover {{
                background: #f1f3f5;
                border-color: #adb5bd;
                color: #212529;
            }}
            QToolButton:pressed {{
                background: #e9ecef;
                border-color: #6c757d;
            }}
            QToolButton:disabled {{
                {StyleManager.EXPORT_BTN_DISABLED_RULES}
            }}
            QToolButton::menu-button {{
                /* Mode MenuButtonPopup : la flèche est centrée dans cette zone
                   (::menu-indicator est ignoré dans ce mode). Élargir la zone
                   éloigne la flèche du bord droit → aération. */
                border: none;
                width: 30px;
            }}
        """

    def _add_seo_buttons(self, layout: QVBoxLayout) -> None:
        """Ajouter les boutons SEO métadonnées"""
        seo_layout = QHBoxLayout()
        
        # Bouton Méta Title — un tiers de la largeur
        self.main_window.meta_title_btn = QPushButton(qta.icon('fa5s.heading', color='#555555'), "Méta Title")
        self.main_window.meta_title_btn.clicked.connect(self.main_window._generate_meta_title)
        self.main_window.meta_title_btn.setEnabled(False)
        self.main_window.meta_title_btn.setToolTip("Générer un méta titre SEO optimisé (largeur affichée par Google sur ordinateur)\nMaj+clic : autre formulation")
        self.main_window.meta_title_btn.setStyleSheet(self._get_seo_title_button_style())
        seo_layout.addWidget(self.main_window.meta_title_btn, 1)
        
        # Bouton Méta Description — un tiers de la largeur
        self.main_window.meta_desc_btn = QPushButton(qta.icon('fa5s.align-left', color='#555555'), "Méta Desc")
        self.main_window.meta_desc_btn.clicked.connect(self.main_window._generate_meta_description)
        self.main_window.meta_desc_btn.setEnabled(False)
        self.main_window.meta_desc_btn.setToolTip("Générer une méta description SEO (largeur affichée par Google sur ordinateur)\nMaj+clic : autre formulation")
        self.main_window.meta_desc_btn.setStyleSheet(self._get_seo_desc_button_style())
        seo_layout.addWidget(self.main_window.meta_desc_btn, 1)

        # Exporter CSV en fin de ligne 2 (v3.99.0 : laisse sa place à "Titre")
        seo_layout.addWidget(self.main_window.export_csv_btn, 1)
        
        layout.addLayout(seo_layout)

    def update_export_buttons_state_by_search(self, is_piece_search: bool) -> None:
        """
        Mettre à jour l'état des boutons d'export selon le type de recherche
        
        Args:
            is_piece_search: True si c'est une recherche de référence de pièce
        """
        # Tous les boutons d'export nécessitent une référence de pièce
        if hasattr(self.main_window, 'export_csv_btn'):
            self.main_window.export_csv_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'export_html_brands_btn'):
            self.main_window.export_html_brands_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'export_html_details_btn'):
            self.main_window.export_html_details_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'copy_csv_btn'):
            self.main_window.copy_csv_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'copy_html_btn'):
            self.main_window.copy_html_btn.setEnabled(is_piece_search)

    # Méthodes de styles pour les boutons
    def _get_csv_button_style(self) -> str:
        """Style pour le bouton CSV"""
        return f"""
            QPushButton {{ 
                background-color: #134c4d; 
                color: white; 
                font-weight: bold; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 4px; 
            }}
            QPushButton:hover {{ 
                background-color: #11403f; 
            }}
            QPushButton:disabled {{ {StyleManager.EXPORT_BTN_DISABLED_RULES} }}
        """
    
    def _get_seo_title_button_style(self) -> str:
        """Style pour le bouton méta title"""
        return f"""
            QPushButton {{ 
                background-color: #fd7e14; 
                color: white; 
                font-weight: bold; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 4px; 
            }}
            QPushButton:hover {{ 
                background-color: #e5711f; 
            }}
            QPushButton:disabled {{ {StyleManager.EXPORT_BTN_DISABLED_RULES} }}
        """
    
    def _get_seo_desc_button_style(self) -> str:
        """Style pour le bouton méta description"""
        return f"""
            QPushButton {{ 
                background-color: #ffc107; 
                color: white; 
                font-weight: bold; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 4px; 
            }}
            QPushButton:hover {{ 
                background-color: #e5a801; 
            }}
            QPushButton:disabled {{ {StyleManager.EXPORT_BTN_DISABLED_RULES} }}
        """
