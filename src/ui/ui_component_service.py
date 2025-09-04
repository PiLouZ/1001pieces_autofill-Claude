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
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QPushButton, QWidget, 
                             QLabel, QSpinBox, QComboBox, QFrame, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

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
        
        # Bouton HTML Détails  
        self.main_window.export_html_details_btn = QPushButton("HTML Détails")
        self.main_window.export_html_details_btn.clicked.connect(
            lambda: self.main_window._export_data(ExportFormat.HTML_DETAILS)
        )
        self.main_window.export_html_details_btn.setEnabled(False)
        export_layout.addWidget(self.main_window.export_html_details_btn)
        
        layout.addLayout(export_layout)
        
        # Ligne 2: Boutons SEO métadonnées
        self._add_seo_buttons(layout)
    
    def _add_seo_buttons(self, layout: QVBoxLayout) -> None:
        """Ajouter les boutons SEO métadonnées"""
        seo_layout = QHBoxLayout()
        
        # Bouton Méta Title - 50% de la largeur
        self.main_window.meta_title_btn = QPushButton("📝 Méta Title")
        self.main_window.meta_title_btn.clicked.connect(self.main_window._generate_meta_title)
        self.main_window.meta_title_btn.setEnabled(False)
        self.main_window.meta_title_btn.setToolTip("Générer un méta titre SEO optimisé (60 caractères max)")
        self.main_window.meta_title_btn.setStyleSheet(self._get_seo_title_button_style())
        seo_layout.addWidget(self.main_window.meta_title_btn, 1)  # stretch factor 1 = 50%
        
        # Bouton Méta Description - 50% de la largeur
        self.main_window.meta_desc_btn = QPushButton("📋 Méta Desc")
        self.main_window.meta_desc_btn.clicked.connect(self.main_window._generate_meta_description)
        self.main_window.meta_desc_btn.setEnabled(False)
        self.main_window.meta_desc_btn.setToolTip("Générer une méta description SEO aléatoire (150 caractères max)")
        self.main_window.meta_desc_btn.setStyleSheet(self._get_seo_desc_button_style())
        seo_layout.addWidget(self.main_window.meta_desc_btn, 1)  # stretch factor 1 = 50%
        
        layout.addLayout(seo_layout)
    
    
    def add_pagination_controls(self, layout: QVBoxLayout) -> None:
        """
        Ajouter les contrôles de pagination modernes
        
        Args:
            layout: Layout parent où ajouter les contrôles
        """
        # Section pagination moderne
        pagination_section = QWidget()
        pagination_section.setObjectName("paginationSection")
        pagination_section.setStyleSheet(self._get_pagination_section_style())
        
        pagination_section_layout = QVBoxLayout(pagination_section)
        pagination_section_layout.setContentsMargins(12, 8, 12, 8)
        
        # Première ligne de pagination
        pagination_layout = QHBoxLayout()
        pagination_layout.setSpacing(4)
        
        # Navigation
        self._add_navigation_buttons(pagination_layout)
        
        # Taille de page
        self._add_page_size_selector(pagination_layout)
        
        pagination_section_layout.addLayout(pagination_layout)
        
        # Deuxième ligne avec indicateurs
        pagination_layout_2 = self._add_pagination_indicators(pagination_layout)
        pagination_section_layout.addLayout(pagination_layout_2)
        
        layout.addWidget(pagination_section)
    
    def _add_navigation_buttons(self, layout: QHBoxLayout) -> None:
        """Ajouter les boutons de navigation"""
        # Première page
        self.main_window.first_page_btn = QPushButton("««")
        self.main_window.first_page_btn.setObjectName("paginationBtn")
        self.main_window.first_page_btn.setToolTip("Première page")
        self.main_window.first_page_btn.clicked.connect(lambda: self.main_window._go_to_page(1))
        layout.addWidget(self.main_window.first_page_btn)
        
        # Page précédente
        self.main_window.prev_page_btn = QPushButton("«")
        self.main_window.prev_page_btn.setObjectName("paginationBtn")
        self.main_window.prev_page_btn.setToolTip("Page précédente")
        self.main_window.prev_page_btn.clicked.connect(self.main_window._previous_page)
        layout.addWidget(self.main_window.prev_page_btn)
        
        # Indicateur de page
        self.main_window.page_info_label = QLabel("Page 1 / 1")
        layout.addWidget(self.main_window.page_info_label)
        
        # Page suivante
        self.main_window.next_page_btn = QPushButton("»")
        self.main_window.next_page_btn.setObjectName("paginationBtn")
        self.main_window.next_page_btn.setToolTip("Page suivante")
        self.main_window.next_page_btn.clicked.connect(self.main_window._next_page)
        layout.addWidget(self.main_window.next_page_btn)
        
        # Dernière page
        self.main_window.last_page_btn = QPushButton("»»")
        self.main_window.last_page_btn.setObjectName("paginationBtn")
        self.main_window.last_page_btn.setToolTip("Dernière page")
        self.main_window.last_page_btn.clicked.connect(self.main_window._go_to_last_page)
        layout.addWidget(self.main_window.last_page_btn)
        
        layout.addWidget(QLabel("|  "))
    
    def _add_page_size_selector(self, layout: QHBoxLayout) -> None:
        """Ajouter le sélecteur de taille de page"""
        layout.addStretch()
        
        # Sélecteur de taille de page aligné à droite
        size_label = QLabel("Afficher:")
        size_label.setObjectName("inlineLabel")
        layout.addWidget(size_label)
        
        self.main_window.page_size_combo = QComboBox()
        self.main_window.page_size_combo.addItems(["500", "1000", "2000", "5000", "10000", "Tout"])
        from src.core.config import Config
        self.main_window.page_size_combo.setCurrentText(str(Config.DEFAULT_PAGE_SIZE))
        self.main_window.page_size_combo.currentTextChanged.connect(self.main_window._change_page_size)
        layout.addWidget(self.main_window.page_size_combo)
    
    def _add_pagination_indicators(self, layout: QHBoxLayout) -> None:
        """Ajouter les indicateurs de pagination - Ligne 2 avec boutons et informations"""
        # Deuxième ligne avec bouton Incomplète centré et informations à droite
        pagination_layout_2 = QHBoxLayout()
        pagination_layout_2.setSpacing(4)
        
        # Espace pour centrer le bouton Incomplète
        pagination_layout_2.addStretch()
        
        # Bouton pour afficher seulement les lignes incomplètes (centré)
        incomplete_btn = QPushButton("📋 Lignes à traiter")
        incomplete_btn.setToolTip("Afficher uniquement les lignes avec des champs vides")
        incomplete_btn.setCheckable(True)
        incomplete_btn.clicked.connect(self.main_window._toggle_incomplete_filter)
        incomplete_btn.setObjectName("incompleteBtn")
        pagination_layout_2.addWidget(incomplete_btn)
        self.main_window.incomplete_filter_btn = incomplete_btn
        
        # Vérifier et masquer le bouton si aucun appareil incomplet
        self.main_window._update_incomplete_button_visibility()
        
        # Espace pour centrer le bouton et pousser les infos à droite
        pagination_layout_2.addStretch()
        
        # Compteur de lignes et indicateur de performance alignés à droite
        self.main_window.counter_label = QLabel("Lignes : 0")
        self.main_window.counter_label.setObjectName("counterLabel")
        pagination_layout_2.addWidget(self.main_window.counter_label)
        
        pagination_layout_2.addWidget(QLabel("  |  "))
        
        # Indicateur de performance
        self.main_window.perf_label = QLabel("⚡ Prêt")
        self.main_window.perf_label.setObjectName("perfLabel")
        pagination_layout_2.addWidget(self.main_window.perf_label)
        
        # Bouton pour afficher toutes les lignes (masqué car option "Tout" existe dans la selectlist)
        self.main_window.show_all_btn = QPushButton("📋 Toutes les lignes")
        self.main_window.show_all_btn.setObjectName("paginationBtn")
        self.main_window.show_all_btn.setToolTip("Afficher toutes les lignes (peut être lent)")
        self.main_window.show_all_btn.clicked.connect(self.main_window._toggle_show_all)
        self.main_window.show_all_btn.setVisible(False)  # Masqué
        pagination_layout_2.addWidget(self.main_window.show_all_btn)
        
        return pagination_layout_2
    
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
    
    def update_export_buttons_state(self, search_term: str) -> None:
        """
        Mettre à jour l'état des boutons d'export selon le terme de recherche
        
        Args:
            search_term: Terme de recherche actuel
        """
        has_search = bool(search_term)
        is_piece_search = has_search and self.main_window._is_piece_reference_search()
        
        # Tous les boutons d'export nécessitent une référence de pièce
        export_buttons = [
            self.main_window.export_csv_btn,
            self.main_window.export_html_brands_btn, 
            self.main_window.export_html_details_btn
        ]
        
        for btn in export_buttons:
            if btn is not None:
                btn.setEnabled(is_piece_search)
        
        # Boutons SEO nécessitent également une référence de pièce
        seo_buttons = [
            getattr(self.main_window, 'meta_title_btn', None),
            getattr(self.main_window, 'meta_desc_btn', None)
        ]
        
        for btn in seo_buttons:
            if btn:
                btn.setEnabled(is_piece_search)
        
    
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
    
    
    def _get_pagination_section_style(self) -> str:
        """Style pour la section pagination"""
        return """
            #paginationSection {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                margin: 5px 0;
            }
        """