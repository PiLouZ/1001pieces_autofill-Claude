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

from ..services.export_service import ExportFormat
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
        # Ligne 1: Boutons d'export traditionnels
        export_layout = QHBoxLayout()
        
        # Bouton Export CSV
        self.main_window.export_csv_btn = QPushButton("Exporter CSV")
        self.main_window.export_csv_btn.clicked.connect(
            lambda: self.main_window._export_data(ExportFormat.CSV)
        )
        self.main_window.export_csv_btn.setEnabled(False)
        self.main_window.export_csv_btn.setStyleSheet(self._get_csv_button_style())
        export_layout.addWidget(self.main_window.export_csv_btn)
        
        # Bouton HTML Marques
        self.main_window.export_html_brands_btn = QPushButton("HTML Marques")
        self.main_window.export_html_brands_btn.clicked.connect(
            lambda: self.main_window._export_data(ExportFormat.HTML_BRANDS)
        )
        self.main_window.export_html_brands_btn.setEnabled(False)
        export_layout.addWidget(self.main_window.export_html_brands_btn)
        
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
        export_layout.addWidget(self.main_window.export_html_details_btn)
        self._refresh_html_details_menu()

        layout.addLayout(export_layout)

        # Ligne 2: Boutons SEO métadonnées
        self._add_seo_buttons(layout)

    def _refresh_html_details_menu(self) -> None:
        """Reconstruire le menu déroulant du bouton "HTML Détails".

        Un seul profil configuré : pas de menu, pas de flèche — clic = export direct.
        Plusieurs profils : la flèche superposée ouvre un menu listant les profils
        AUTRES que celui par défaut (le clic principal exporte déjà ce dernier).
        """
        btn = self.main_window.export_html_details_btn
        svc = getattr(self.main_window, 'export_config_service', None)
        names = svc.get_details_profile_names() if svc else []

        if len(names) <= 1:
            btn.setMenu(None)
            btn.setPopupMode(QToolButton.DelayedPopup)
            return

        default_name = svc.get_default_details_profile_name()
        menu = QMenu(btn)
        for name in names:
            if name == default_name:
                continue
            action = menu.addAction(name)
            action.setData(name)
        menu.triggered.connect(self._on_html_details_profile_chosen)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.MenuButtonPopup)

    def _on_html_details_profile_chosen(self, action) -> None:
        """Export HTML Détails avec le profil choisi dans le menu déroulant."""
        self.main_window._export_data(ExportFormat.HTML_DETAILS, profile_name=action.data())

    def _on_export_html_details_clicked(self):
        """Clic sur le bouton principal "HTML Détails" : export immédiat avec
        le profil par défaut (ou l'unique profil configuré)."""
        svc = getattr(self.main_window, 'export_config_service', None)
        default_name = svc.get_default_details_profile_name() if svc else None
        self.main_window._export_data(ExportFormat.HTML_DETAILS, profile_name=default_name)

    def _get_split_button_style(self) -> str:
        """Style du bouton split "HTML Détails" — aligné sur le QPushButton global."""
        return """
            QToolButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #ffffff, stop: 1 #f8f9fa);
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 500;
                color: #495057;
            }
            QToolButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #e9ecef, stop: 1 #dee2e6);
                border-color: #adb5bd;
                color: #212529;
            }
            QToolButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #dee2e6, stop: 1 #ced4da);
                border-color: #6c757d;
            }
            QToolButton:disabled {
                background-color: #f8f9fa;
                color: #6c757d;
                border-color: #e9ecef;
            }
            QToolButton::menu-button {
                /* Mode MenuButtonPopup : la flèche est centrée dans cette zone
                   (::menu-indicator est ignoré dans ce mode). Élargir la zone
                   éloigne la flèche du bord droit → aération. */
                border: none;
                width: 30px;
            }
        """

    def _add_seo_buttons(self, layout: QVBoxLayout) -> None:
        """Ajouter les boutons SEO métadonnées"""
        seo_layout = QHBoxLayout()
        
        # Bouton Méta Title - 50% de la largeur
        self.main_window.meta_title_btn = QPushButton(qta.icon('fa5s.heading', color='#555555'), "Méta Title")
        self.main_window.meta_title_btn.clicked.connect(self.main_window._generate_meta_title)
        self.main_window.meta_title_btn.setEnabled(False)
        self.main_window.meta_title_btn.setToolTip("Générer un méta titre SEO optimisé (60 caractères max)")
        self.main_window.meta_title_btn.setStyleSheet(self._get_seo_title_button_style())
        seo_layout.addWidget(self.main_window.meta_title_btn, 1)  # stretch factor 1 = 50%
        
        # Bouton Méta Description - 50% de la largeur
        self.main_window.meta_desc_btn = QPushButton(qta.icon('fa5s.align-left', color='#555555'), "Méta Desc")
        self.main_window.meta_desc_btn.clicked.connect(self.main_window._generate_meta_description)
        self.main_window.meta_desc_btn.setEnabled(False)
        self.main_window.meta_desc_btn.setToolTip("Générer une méta description SEO aléatoire (150 caractères max)")
        self.main_window.meta_desc_btn.setStyleSheet(self._get_seo_desc_button_style())
        seo_layout.addWidget(self.main_window.meta_desc_btn, 1)  # stretch factor 1 = 50%
        
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
        return """
            QPushButton { 
                background-color: #134c4d; 
                color: white; 
                font-weight: bold; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #11403f; 
            }
            QPushButton:disabled { 
                background-color: #cccccc; 
                color: #666666; 
            }
        """
    
    def _get_seo_title_button_style(self) -> str:
        """Style pour le bouton méta title"""
        return """
            QPushButton { 
                background-color: #fd7e14; 
                color: white; 
                font-weight: bold; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #e5711f; 
            }
            QPushButton:disabled { 
                background-color: #cccccc; 
                color: #666666; 
            }
        """
    
    def _get_seo_desc_button_style(self) -> str:
        """Style pour le bouton méta description"""
        return """
            QPushButton { 
                background-color: #ffc107; 
                color: white; 
                font-weight: bold; 
                border: none; 
                padding: 8px 12px; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #e5a801; 
            }
            QPushButton:disabled { 
                background-color: #cccccc; 
                color: #666666; 
            }
        """
