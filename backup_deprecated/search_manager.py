"""
SearchManager - Refactorisation Phase 3
Extraction de la logique de recherche de MainWindow

RESPONSABILITÉS :
- Gestion des recherches simples et avancées
- Configuration et connection des signaux de recherche
- Gestion du nettoyage automatique des données de recherche
- Interface avec AdvancedSearchService et SearchService
- Détection du type de recherche (pièce, référence, etc.)

OBJECTIF : Réduire MainWindow en extrayant ~20 méthodes liées aux recherches
"""

from typing import Optional, Dict, Any, List
from PyQt5.QtWidgets import QLineEdit, QWidget
from PyQt5.QtCore import QObject, pyqtSignal, QMimeData
from PyQt5.QtGui import QKeyEvent

from ..core.logger import app_logger
from ..core.config import Config


class SearchInputWidget(QLineEdit):
    """
    Widget d'entrée de recherche avec nettoyage automatique des données collées
    
    Extrait de la classe interne PasteInterceptor dans MainWindow
    """
    
    def __init__(self, parent_window, paste_service):
        super().__init__()
        self.parent_window = parent_window
        self.paste_service = paste_service
        
    def keyPressEvent(self, event: QKeyEvent):
        """Gérer les événements clavier avec nettoyage automatique"""
        if event.key() == 16777220:  # Touche Entrée
            # Nettoyer automatiquement avant la recherche si configuré
            if hasattr(self.paste_service, 'cleanup_enabled') and self.paste_service.cleanup_enabled:
                self._handle_paste_event()
        super().keyPressEvent(event)
    
    def insertFromMimeData(self, source: QMimeData):
        """Intercepter et nettoyer les données collées"""
        if source.hasText():
            original_text = source.text()
            
            # Appliquer le nettoyage automatique si activé
            if (hasattr(self.paste_service, 'cleanup_enabled') 
                and self.paste_service.cleanup_enabled
                and hasattr(self.paste_service, 'clean_text')):
                
                cleaned_text = self.paste_service.clean_text(original_text)
                
                # Créer un nouveau QMimeData avec le texte nettoyé
                cleaned_mime = QMimeData()
                cleaned_mime.setText(cleaned_text)
                super().insertFromMimeData(cleaned_mime)
            else:
                super().insertFromMimeData(source)
        else:
            super().insertFromMimeData(source)
    
    def _handle_paste_event(self):
        """Gérer l'événement de collage avec nettoyage"""
        current_text = self.text()
        if (current_text 
            and hasattr(self.paste_service, 'clean_text')):
            cleaned_text = self.paste_service.clean_text(current_text)
            if cleaned_text != current_text:
                self.setText(cleaned_text)
                app_logger.debug(f"Texte de recherche nettoyé : '{current_text}' → '{cleaned_text}'")


class SearchManager(QObject):
    """
    Gestionnaire spécialisé pour toutes les opérations de recherche
    
    Extrait les responsabilités de recherche de MainWindow :
    - Configuration des services de recherche
    - Gestion des événements de recherche
    - Types de recherche et détection
    - Interface avec les services avancés
    """
    
    # Signaux pour communication avec MainWindow
    search_initiated = pyqtSignal(str)  # Signal émis quand une recherche commence
    search_type_detected = pyqtSignal(str, dict)  # Signal pour le type de recherche détecté
    search_results_ready = pyqtSignal(list)  # Signal quand les résultats sont prêts
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.search_input = None
        self._is_initialized = False
        
        # Références vers les services nécessaires
        self.search_service = None
        self.advanced_search_service = None
        self.paste_cleanup_service = None
    
    def initialize(self, search_service, advanced_search_service, paste_cleanup_service):
        """
        Initialiser le gestionnaire avec les services nécessaires
        
        Args:
            search_service: Service de recherche de base
            advanced_search_service: Service de recherche avancée
            paste_cleanup_service: Service de nettoyage automatique
        """
        self.search_service = search_service
        self.advanced_search_service = advanced_search_service
        self.paste_cleanup_service = paste_cleanup_service
        
        self._setup_search_input()
        self._connect_advanced_search_signals()
        
        self._is_initialized = True
        app_logger.info("SearchManager initialisé avec succès")
    
    def _setup_search_input(self):
        """
        Configurer le widget d'entrée de recherche avec nettoyage automatique
        
        Méthode extraite de MainWindow._setup_paste_cleanup_for_search_input()
        """
        try:
            if not self.paste_cleanup_service:
                app_logger.warning("PasteCleanupService non disponible")
                return
            
            # Créer le widget d'entrée personnalisé
            self.search_input = SearchInputWidget(self.main_window, self.paste_cleanup_service)
            self.search_input.setPlaceholderText("🔍 Rechercher par modèle, marque, référence...")
            
            # Configuration du style
            self.search_input.setStyleSheet("""
                QLineEdit {
                    padding: 8px 12px;
                    border: 2px solid #e0e6ed;
                    border-radius: 6px;
                    font-size: 14px;
                    background: white;
                    selection-background-color: #007bff;
                }
                QLineEdit:focus {
                    border-color: #007bff;
                    outline: none;
                    box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.1);
                }
                QLineEdit:hover {
                    border-color: #b6d0ff;
                }
            """)
            
            app_logger.debug("Widget de recherche configuré avec nettoyage automatique")
            
        except Exception as e:
            app_logger.error(f"Erreur configuration search input: {e}")
            # Fallback vers un QLineEdit standard
            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("🔍 Rechercher...")
    
    def _connect_advanced_search_signals(self):
        """
        Connecter les signaux du service de recherche avancée
        
        Méthode extraite de MainWindow._connect_advanced_search_signals()
        """
        try:
            if not self.advanced_search_service:
                app_logger.warning("AdvancedSearchService non disponible")
                return
            
            # Connecter les signaux de résultats
            if hasattr(self.advanced_search_service, 'results_ready'):
                self.advanced_search_service.results_ready.connect(self._on_search_results_ready)
            
            # Connecter les signaux de mise à jour de statut
            if hasattr(self.advanced_search_service, 'search_status_updated'):
                self.advanced_search_service.search_status_updated.connect(self._on_search_status_updated)
            
            # Connecter les signaux d'erreur
            if hasattr(self.advanced_search_service, 'search_error'):
                self.advanced_search_service.search_error.connect(self._on_search_error)
            
            app_logger.debug("Signaux AdvancedSearchService connectés")
            
        except Exception as e:
            app_logger.error(f"Erreur connection signaux recherche avancée: {e}")
    
    def get_search_input_widget(self) -> QLineEdit:
        """
        Obtenir le widget d'entrée de recherche
        
        Returns:
            QLineEdit: Widget d'entrée configuré ou None si pas initialisé
        """
        if not self._is_initialized:
            app_logger.warning("SearchManager non initialisé")
            return None
        return self.search_input
    
    def is_piece_reference_search(self) -> bool:
        """
        Détecter si la recherche actuelle est une recherche de référence de pièce
        
        Méthode extraite de MainWindow._is_piece_reference_search()
        
        Returns:
            bool: True si c'est une recherche de référence de pièce
        """
        try:
            if not self.search_input:
                return False
            
            search_term = self.search_input.text().strip()
            if not search_term:
                return False
            
            # Logique de détection basée sur des patterns
            # (à adapter selon les besoins spécifiques de l'application)
            
            # Critères pour une référence de pièce :
            # - Contient des chiffres et lettres
            # - Longueur raisonnable (3-20 caractères)
            # - Pas d'espaces multiples ou caractères spéciaux excessifs
            
            import re
            
            # Pattern basique pour référence : lettres + chiffres
            if re.match(r'^[A-Za-z0-9\-_\.]{3,20}$', search_term):
                return True
            
            # Pattern pour référence avec espaces limités
            if re.match(r'^[A-Za-z0-9\-_\.\s]{3,25}$', search_term) and search_term.count(' ') <= 2:
                return True
            
            return False
            
        except Exception as e:
            app_logger.error(f"Erreur détection recherche référence: {e}")
            return False
    
    def get_current_search_term(self) -> str:
        """
        Obtenir le terme de recherche actuel
        
        Returns:
            str: Terme de recherche ou chaîne vide
        """
        if self.search_input:
            return self.search_input.text().strip()
        return ""
    
    def set_search_term(self, term: str):
        """
        Définir le terme de recherche
        
        Args:
            term: Nouveau terme de recherche
        """
        if self.search_input:
            self.search_input.setText(term)
            app_logger.debug(f"Terme de recherche défini: '{term}'")
    
    def clear_search(self):
        """Vider le champ de recherche"""
        if self.search_input:
            self.search_input.clear()
            app_logger.debug("Champ de recherche vidé")
    
    def initiate_search(self, term: Optional[str] = None):
        """
        Initier une recherche
        
        Args:
            term: Terme de recherche optionnel (utilise l'input actuel si None)
        """
        try:
            search_term = term if term is not None else self.get_current_search_term()
            
            if not search_term:
                app_logger.warning("Tentative de recherche avec terme vide")
                return
            
            # Détecter le type de recherche
            is_piece_ref = self.is_piece_reference_search()
            search_type = "piece_reference" if is_piece_ref else "general"
            
            # Émettre les signaux
            self.search_initiated.emit(search_term)
            self.search_type_detected.emit(search_type, {"term": search_term, "is_piece_ref": is_piece_ref})
            
            app_logger.info(f"Recherche initiée: '{search_term}' (type: {search_type})")
            
        except Exception as e:
            app_logger.error(f"Erreur initiation recherche: {e}")
    
    def reload_current_search(self):
        """
        Recharger la recherche courante
        
        Méthode extraite de MainWindow._reload_current_search()
        """
        try:
            current_term = self.get_current_search_term()
            if current_term:
                self.initiate_search(current_term)
                app_logger.debug(f"Recherche rechargée: '{current_term}'")
            else:
                app_logger.warning("Aucune recherche courante à recharger")
                
        except Exception as e:
            app_logger.error(f"Erreur rechargement recherche: {e}")
    
    def _on_search_results_ready(self, results: List):
        """
        Gérer les résultats de recherche prêts
        
        Args:
            results: Liste des résultats de recherche
        """
        try:
            app_logger.debug(f"Résultats de recherche reçus: {len(results)} éléments")
            self.search_results_ready.emit(results)
            
        except Exception as e:
            app_logger.error(f"Erreur traitement résultats recherche: {e}")
    
    def _on_search_status_updated(self, status: str, details: Dict[str, Any]):
        """
        Gérer les mises à jour de statut de recherche
        
        Args:
            status: Statut de la recherche
            details: Détails additionnels
        """
        try:
            app_logger.debug(f"Statut recherche mis à jour: {status}")
            # Logique de traitement du statut si nécessaire
            
        except Exception as e:
            app_logger.error(f"Erreur traitement statut recherche: {e}")
    
    def _on_search_error(self, error: str, details: Dict[str, Any]):
        """
        Gérer les erreurs de recherche
        
        Args:
            error: Message d'erreur
            details: Détails de l'erreur
        """
        try:
            app_logger.error(f"Erreur de recherche: {error}")
            # Émettre un signal d'erreur si nécessaire ou gérer l'erreur
            
        except Exception as e:
            app_logger.error(f"Erreur traitement erreur recherche: {e}")
    
    def get_advanced_search_term_with_fallback(self) -> Optional[str]:
        """
        Obtenir le terme de recherche avancée avec fallback
        
        Returns:
            str: Terme de recherche avancée ou terme simple si non disponible
        """
        try:
            if (self.advanced_search_service 
                and hasattr(self.advanced_search_service, 'get_current_search_term_with_fallback')):
                return self.advanced_search_service.get_current_search_term_with_fallback(self.main_window)
            
            # Fallback vers terme simple
            return self.get_current_search_term()
            
        except Exception as e:
            app_logger.error(f"Erreur récupération terme recherche avancée: {e}")
            return self.get_current_search_term()
    
    def cleanup(self):
        """Nettoyer les ressources du gestionnaire"""
        try:
            # Déconnecter les signaux
            if self.advanced_search_service and hasattr(self.advanced_search_service, 'results_ready'):
                self.advanced_search_service.results_ready.disconnect(self._on_search_results_ready)
            
            app_logger.debug("SearchManager nettoyé")
            
        except Exception as e:
            app_logger.error(f"Erreur nettoyage SearchManager: {e}")