"""
TableManager - Refactorisation Phase 3  
Extraction de la logique de gestion du tableau de MainWindow

RESPONSABILITÉS :
- Gestion du tri des colonnes et indicateurs visuels
- Gestion de la pagination (navigation, contrôles)
- Numérotation des lignes et mise à jour dynamique
- Configuration et visibilité des colonnes
- Gestion des événements de tri et navigation

OBJECTIF : Réduire MainWindow en extrayant ~15 méthodes liées au tableau
"""

from typing import Optional, Dict, Any, List, Tuple
from PyQt5.QtWidgets import (QWidget, QTableWidget, QLabel, QPushButton, 
                           QComboBox, QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy)
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtGui import QFont

from ..core.logger import app_logger
from ..core.config import Config


class PaginationControls(QWidget):
    """
    Widget de contrôles de pagination
    
    Extrait de la logique de pagination de MainWindow
    """
    
    # Signaux pour communication avec le gestionnaire parent
    page_changed = pyqtSignal(int)  # Nouvelle page sélectionnée
    page_size_changed = pyqtSignal(int)  # Nouvelle taille de page
    show_all_requested = pyqtSignal()  # Demande d'affichage de tous les éléments
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.current_page = 1
        self.total_pages = 1
        self.page_size = Config.PAGE_SIZE
        self.total_items = 0
    
    def _setup_ui(self):
        """Créer l'interface des contrôles de pagination"""
        layout = QHBoxLayout()
        
        # Bouton page précédente
        self.prev_button = QPushButton("◀ Précédent")
        self.prev_button.clicked.connect(self._previous_page)
        self.prev_button.setEnabled(False)
        layout.addWidget(self.prev_button)
        
        # Informations page courante
        self.page_info_label = QLabel("Page 1 sur 1")
        self.page_info_label.setStyleSheet("font-weight: bold; margin: 0 10px;")
        layout.addWidget(self.page_info_label)
        
        # Bouton page suivante
        self.next_button = QPushButton("Suivant ▶")
        self.next_button.clicked.connect(self._next_page)
        self.next_button.setEnabled(False)
        layout.addWidget(self.next_button)
        
        # Spacer
        spacer = QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addItem(spacer)
        
        # Sélecteur taille de page
        layout.addWidget(QLabel("Éléments par page :"))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["10", "25", "50", "100", "Tout"])
        self.page_size_combo.setCurrentText(str(Config.PAGE_SIZE))
        self.page_size_combo.currentTextChanged.connect(self._change_page_size)
        layout.addWidget(self.page_size_combo)
        
        # Bouton dernière page
        self.last_page_button = QPushButton("Dernière")
        self.last_page_button.clicked.connect(self._go_to_last_page)
        layout.addWidget(self.last_page_button)
        
        # Bouton tout afficher
        self.show_all_button = QPushButton("📋 Tout afficher")
        self.show_all_button.setCheckable(True)
        self.show_all_button.clicked.connect(self._toggle_show_all)
        layout.addWidget(self.show_all_button)
        
        self.setLayout(layout)
    
    def update_pagination_info(self, current_page: int, total_pages: int, total_items: int, page_size: int):
        """
        Mettre à jour les informations de pagination
        
        Args:
            current_page: Page actuelle
            total_pages: Nombre total de pages
            total_items: Nombre total d'éléments
            page_size: Taille de page actuelle
        """
        try:
            self.current_page = current_page
            self.total_pages = total_pages
            self.total_items = total_items
            self.page_size = page_size
            
            # Mettre à jour le label d'information
            if total_items == 0:
                self.page_info_label.setText("Aucun résultat")
            elif page_size >= total_items:  # Mode "Tout afficher"
                self.page_info_label.setText(f"{total_items} éléments")
            else:
                start_item = (current_page - 1) * page_size + 1
                end_item = min(current_page * page_size, total_items)
                self.page_info_label.setText(f"Page {current_page}/{total_pages} ({start_item}-{end_item} sur {total_items})")
            
            # Activer/désactiver les boutons
            self.prev_button.setEnabled(current_page > 1)
            self.next_button.setEnabled(current_page < total_pages)
            self.last_page_button.setEnabled(total_pages > 1)
            
            # Mettre à jour l'état du bouton "Tout afficher"
            is_showing_all = page_size >= total_items
            self.show_all_button.setChecked(is_showing_all)
            
            app_logger.debug(f"Pagination mise à jour: page {current_page}/{total_pages}, {total_items} éléments")
            
        except Exception as e:
            app_logger.error(f"Erreur mise à jour pagination: {e}")
    
    def _previous_page(self):
        """Aller à la page précédente"""
        if self.current_page > 1:
            new_page = self.current_page - 1
            self.page_changed.emit(new_page)
    
    def _next_page(self):
        """Aller à la page suivante"""
        if self.current_page < self.total_pages:
            new_page = self.current_page + 1
            self.page_changed.emit(new_page)
    
    def _go_to_last_page(self):
        """Aller à la dernière page"""
        if self.total_pages > 1:
            self.page_changed.emit(self.total_pages)
    
    def _change_page_size(self, size_text: str):
        """Changer la taille de page"""
        try:
            if size_text == "Tout":
                # Émettre signal pour tout afficher
                self.show_all_requested.emit()
            else:
                new_size = int(size_text)
                self.page_size_changed.emit(new_size)
                app_logger.debug(f"Taille de page changée: {new_size}")
                
        except ValueError:
            app_logger.error(f"Taille de page invalide: {size_text}")
    
    def _toggle_show_all(self):
        """Basculer entre pagination et affichage complet"""
        if self.show_all_button.isChecked():
            self.show_all_requested.emit()
        else:
            # Revenir à la pagination normale
            self.page_size_changed.emit(Config.PAGE_SIZE)


class TableManager(QObject):
    """
    Gestionnaire spécialisé pour toutes les opérations sur le tableau
    
    Extrait les responsabilités de tableau de MainWindow :
    - Gestion du tri des colonnes
    - Pagination et navigation
    - Numérotation des lignes
    - Contrôles de visibilité des colonnes
    - Événements de tableau
    """
    
    # Signaux pour communication avec MainWindow
    sort_requested = pyqtSignal(int, str)  # colonne, ordre (ASC/DESC)
    page_navigation_requested = pyqtSignal(int)  # nouvelle page
    page_size_changed = pyqtSignal(int)  # nouvelle taille de page
    show_all_toggled = pyqtSignal(bool)  # basculer affichage complet
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.table_widget = None
        self.pagination_controls = None
        
        # État du tri
        self.current_sort_column = -1
        self.current_sort_order = "ASC"
        
        # État de la pagination
        self.current_page = 1
        self.total_pages = 1
        self.page_size = Config.PAGE_SIZE
        self.total_items = 0
        self.use_pagination = True
        
        self._is_initialized = False
    
    def initialize(self, table_widget: QTableWidget):
        """
        Initialiser le gestionnaire avec le widget de tableau
        
        Args:
            table_widget: Widget de tableau à gérer
        """
        self.table_widget = table_widget
        self._setup_table_connections()
        self._setup_pagination_controls()
        self._is_initialized = True
        app_logger.info("TableManager initialisé avec succès")
    
    def _setup_table_connections(self):
        """Configurer les connexions du tableau"""
        try:
            if self.table_widget:
                # Connecter les événements de tri
                header = self.table_widget.horizontalHeader()
                if header:
                    header.sectionClicked.connect(self._on_header_clicked)
                    app_logger.debug("Événements de tri connectés")
                    
        except Exception as e:
            app_logger.error(f"Erreur configuration connexions tableau: {e}")
    
    def _setup_pagination_controls(self):
        """Créer et configurer les contrôles de pagination"""
        try:
            self.pagination_controls = PaginationControls()
            
            # Connecter les signaux de pagination
            self.pagination_controls.page_changed.connect(self._on_page_changed)
            self.pagination_controls.page_size_changed.connect(self._on_page_size_changed)
            self.pagination_controls.show_all_requested.connect(self._on_show_all_requested)
            
            app_logger.debug("Contrôles de pagination configurés")
            
        except Exception as e:
            app_logger.error(f"Erreur création contrôles pagination: {e}")
    
    def get_pagination_controls_widget(self) -> Optional[QWidget]:
        """
        Obtenir le widget des contrôles de pagination
        
        Returns:
            QWidget: Widget des contrôles ou None si pas initialisé
        """
        if not self._is_initialized or not self.pagination_controls:
            app_logger.warning("TableManager non initialisé ou contrôles manquants")
            return None
        return self.pagination_controls
    
    def _on_header_clicked(self, logical_index: int):
        """
        Gérer le clic sur un en-tête de colonne pour le tri
        
        Méthode extraite de MainWindow._on_header_clicked()
        
        Args:
            logical_index: Index logique de la colonne cliquée
        """
        try:
            # Déterminer le nouvel ordre de tri
            if self.current_sort_column == logical_index:
                # Basculer l'ordre si même colonne
                new_order = "DESC" if self.current_sort_order == "ASC" else "ASC"
            else:
                # Nouvelle colonne, commencer par ASC
                new_order = "ASC"
            
            self.current_sort_column = logical_index
            self.current_sort_order = new_order
            
            # Émettre signal pour demander le tri
            self.sort_requested.emit(logical_index, new_order)
            
            # Mettre à jour les indicateurs visuels
            self._update_sort_indicators()
            
            app_logger.debug(f"Tri demandé: colonne {logical_index}, ordre {new_order}")
            
        except Exception as e:
            app_logger.error(f"Erreur gestion clic en-tête: {e}")
    
    def _update_sort_indicators(self):
        """
        Mettre à jour les indicateurs visuels de tri
        
        Méthode extraite de MainWindow._update_sort_indicators()
        """
        try:
            if not self.table_widget:
                return
            
            header = self.table_widget.horizontalHeader()
            if not header:
                return
            
            # Effacer tous les indicateurs existants
            for col in range(header.count()):
                current_text = self.table_widget.horizontalHeaderItem(col)
                if current_text:
                    text = current_text.text()
                    # Supprimer les anciens indicateurs
                    text = text.replace(" ↑", "").replace(" ↓", "")
                    current_text.setText(text)
            
            # Ajouter l'indicateur pour la colonne triée
            if (self.current_sort_column >= 0 
                and self.current_sort_column < header.count()):
                
                sorted_header = self.table_widget.horizontalHeaderItem(self.current_sort_column)
                if sorted_header:
                    text = sorted_header.text().replace(" ↑", "").replace(" ↓", "")
                    indicator = " ↑" if self.current_sort_order == "ASC" else " ↓"
                    sorted_header.setText(text + indicator)
            
            app_logger.debug(f"Indicateurs de tri mis à jour: colonne {self.current_sort_column}")
            
        except Exception as e:
            app_logger.error(f"Erreur mise à jour indicateurs tri: {e}")
    
    def update_row_numbers(self):
        """
        Mettre à jour la numérotation des lignes
        
        Méthode extraite de MainWindow._update_row_numbers()
        """
        try:
            if not self.table_widget:
                return
            
            row_count = self.table_widget.rowCount()
            start_number = (self.current_page - 1) * self.page_size + 1 if self.use_pagination else 1
            
            for row in range(row_count):
                row_number = start_number + row
                self.table_widget.setVerticalHeaderItem(row, self.table_widget.verticalHeaderItem(row))
                
                # Mettre à jour l'en-tête vertical avec le numéro
                item = self.table_widget.verticalHeaderItem(row)
                if item:
                    item.setText(str(row_number))
                else:
                    from PyQt5.QtWidgets import QTableWidgetItem
                    new_item = QTableWidgetItem(str(row_number))
                    self.table_widget.setVerticalHeaderItem(row, new_item)
            
            app_logger.debug(f"Numérotation des lignes mise à jour: {row_count} lignes")
            
        except Exception as e:
            app_logger.error(f"Erreur mise à jour numérotation: {e}")
    
    def update_pagination_info(self, current_page: int, total_pages: int, total_items: int):
        """
        Mettre à jour les informations de pagination
        
        Args:
            current_page: Page actuelle
            total_pages: Nombre total de pages  
            total_items: Nombre total d'éléments
        """
        try:
            self.current_page = current_page
            self.total_pages = total_pages
            self.total_items = total_items
            
            if self.pagination_controls:
                self.pagination_controls.update_pagination_info(
                    current_page, total_pages, total_items, self.page_size
                )
            
            # Mettre à jour la numérotation des lignes
            self.update_row_numbers()
            
            app_logger.debug(f"Pagination mise à jour: page {current_page}/{total_pages}")
            
        except Exception as e:
            app_logger.error(f"Erreur mise à jour pagination: {e}")
    
    def _on_page_changed(self, new_page: int):
        """Gérer le changement de page"""
        try:
            if 1 <= new_page <= self.total_pages:
                self.current_page = new_page
                self.page_navigation_requested.emit(new_page)
                app_logger.debug(f"Navigation page: {new_page}")
            else:
                app_logger.warning(f"Page invalide demandée: {new_page}")
                
        except Exception as e:
            app_logger.error(f"Erreur changement page: {e}")
    
    def _on_page_size_changed(self, new_size: int):
        """Gérer le changement de taille de page"""
        try:
            if new_size > 0:
                self.page_size = new_size
                self.use_pagination = True
                self.page_size_changed.emit(new_size)
                app_logger.debug(f"Taille de page changée: {new_size}")
            else:
                app_logger.warning(f"Taille de page invalide: {new_size}")
                
        except Exception as e:
            app_logger.error(f"Erreur changement taille page: {e}")
    
    def _on_show_all_requested(self):
        """Gérer la demande d'affichage de tous les éléments"""
        try:
            self.use_pagination = not self.pagination_controls.show_all_button.isChecked()
            self.show_all_toggled.emit(not self.use_pagination)
            app_logger.debug(f"Basculement affichage complet: {not self.use_pagination}")
            
        except Exception as e:
            app_logger.error(f"Erreur basculement affichage complet: {e}")
    
    def apply_database_sort(self, sort_callback):
        """
        Appliquer le tri au niveau base de données
        
        Args:
            sort_callback: Fonction callback pour effectuer le tri
        """
        try:
            if self.current_sort_column >= 0 and sort_callback:
                sort_callback(self.current_sort_column, self.current_sort_order)
                self._update_sort_indicators()
                app_logger.debug("Tri base de données appliqué")
                
        except Exception as e:
            app_logger.error(f"Erreur application tri BDD: {e}")
    
    def get_current_sort_info(self) -> Tuple[int, str]:
        """
        Obtenir les informations de tri actuelles
        
        Returns:
            Tuple[int, str]: (colonne, ordre) du tri actuel
        """
        return (self.current_sort_column, self.current_sort_order)
    
    def get_current_pagination_info(self) -> Dict[str, Any]:
        """
        Obtenir les informations de pagination actuelles
        
        Returns:
            Dict: Informations complètes de pagination
        """
        return {
            'current_page': self.current_page,
            'total_pages': self.total_pages,
            'page_size': self.page_size,
            'total_items': self.total_items,
            'use_pagination': self.use_pagination
        }
    
    def cleanup(self):
        """Nettoyer les ressources du gestionnaire"""
        try:
            # Déconnecter les signaux
            if self.table_widget:
                header = self.table_widget.horizontalHeader()
                if header:
                    header.sectionClicked.disconnect(self._on_header_clicked)
            
            if self.pagination_controls:
                self.pagination_controls.page_changed.disconnect(self._on_page_changed)
                self.pagination_controls.page_size_changed.disconnect(self._on_page_size_changed)
                self.pagination_controls.show_all_requested.disconnect(self._on_show_all_requested)
            
            app_logger.debug("TableManager nettoyé")
            
        except Exception as e:
            app_logger.error(f"Erreur nettoyage TableManager: {e}")