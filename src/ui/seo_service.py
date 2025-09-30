"""
Service SEO - Phase 2.15
Extrait de main_refactored.py pour centraliser la logique de génération SEO

Responsabilités:
- Génération de méta titles et descriptions optimisées SEO
- Récupération et analyse des données de recherche pour SEO
- Gestion des multi-références dans la génération SEO
- Interface avec le SEOGenerator pour optimisation du contenu
- Validation et formatage des données pour l'optimisation SEO
"""

from typing import Optional, Dict, Any, List, Tuple
from .qt_imports import QInputDialog, QApplication
from .qt_imports import QTimer

from src.core.config import Config
from src.core.logger import app_logger
from src.utils.seo_generator import SEOGenerator
from src.utils.error_handler import handle_seo_generation_errors, handle_seo_data_errors, handle_seo_dialog_errors

class SEOService:
    """
    Service spécialisé pour la génération et optimisation SEO
    
    Responsabilités:
    - Génération de méta titles et descriptions optimisées
    - Analyse des données de recherche pour contexte SEO
    - Gestion des multi-références et sélection utilisateur  
    - Interface utilisateur pour fonctionnalités SEO
    - Validation et optimisation du contenu généré
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.seo_generator = SEOGenerator()
    
    @handle_seo_generation_errors()
    def generate_meta_title(self) -> None:
        """Générer et copier un méta titre SEO optimisé - Logique originale restaurée"""
        # Gérer les recherches multi-références
        multi_terms = self._get_multi_reference_terms()
        if multi_terms:
            # Demander à l'utilisateur de choisir la référence pour la génération SEO
            selected_reference = self._show_reference_selection_dialog(
                "Référence pour Méta Title",
                f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                f"Choisissez la référence à utiliser pour la génération SEO :",
                multi_terms[0]  # Premier terme par défaut
            )
            
            if not selected_reference:
                return  # Annulé par l'utilisateur
            
            # Récupérer les données pour la référence sélectionnée
            search_data = self._get_current_search_data_for_reference(selected_reference)
        else:
            # Récupérer les données de recherche actuelles (comportement normal)
            search_data = self._get_current_search_data()
        
        if not search_data:
            self.main_window.statusbar.showMessage("Aucune recherche active pour générer le méta titre", 3000)
            return
        
        # Générer le méta titre avec la logique originale
        result = self.seo_generator.generate_meta_title(
            reference=search_data['reference'],
            description=search_data['description'], 
            type_appareil=search_data['type_appareil'],
            fabricants=search_data['fabricants']
        )
        
        # Copier dans le presse-papiers
        from .qt_imports import QApplication
        QApplication.clipboard().setText(result['title'])
        
        # Message de statut avec informations détaillées
        length = result['length']
        fabricants_info = f"({result['info']['fabricants_count']} fabricants)" if result['info']['fabricants_count'] > 0 else ""
        
        status_msg = f"Méta titre copié ({length}/60 caractères) {fabricants_info}"
        if result['info']['truncated']:
            status_msg += " [Tronqué]"
        
        # Reporter dans l'historique
        detailed_message = f"SEO: Méta titre généré pour '{search_data['reference']}'"
        detailed_message += f"\n==> Titre: {result['title']}"
        detailed_message += f"\n==> Longueur: {length}/60 caractères"
        if result['info']['fabricants_count'] > 0:
            detailed_message += f"\n==> Fabricants inclus: {result['info']['fabricants_count']}"
        if result['info']['truncated']:
            detailed_message += "\n==> Titre tronqué"
        
        self.main_window.user_interaction_service.add_to_history(detailed_message)
        
        # Message statusbar
        self.main_window.statusbar.showMessage(status_msg, 3000)
            
        
    
    def generate_meta_description(self) -> None:
        """Générer et copier une méta description SEO aléatoire - Logique originale restaurée"""
        try:
            # Gérer les recherches multi-références
            multi_terms = self._get_multi_reference_terms()
            if multi_terms:
                # Demander à l'utilisateur de choisir la référence pour la génération SEO
                selected_reference = self._show_reference_selection_dialog(
                    "Référence pour Méta Description",
                    f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                    f"Choisissez la référence à utiliser pour la génération SEO :",
                    multi_terms[0]  # Premier terme par défaut
                )
                
                if not selected_reference:
                    return  # Annulé par l'utilisateur
                
                # Récupérer les données pour la référence sélectionnée
                search_data = self._get_current_search_data_for_reference(selected_reference)
            else:
                # Récupérer les données de recherche actuelles (comportement normal)
                search_data = self._get_current_search_data()
            
            if not search_data:
                self.main_window.statusbar.showMessage("Aucune recherche active pour générer la méta description", 3000)
                return
            
            # Générer la méta description avec la logique originale
            result = self.seo_generator.generate_meta_description(
                reference=search_data['reference'],
                description=search_data['description'],
                type_appareil=search_data['type_appareil'],
                fabricants=search_data['fabricants']
            )
            
            # Copier dans le presse-papiers
            from .qt_imports import QApplication
            QApplication.clipboard().setText(result['description'])
            
            # Message de statut avec informations détaillées
            length = result['length']
            status_msg = f"Méta description copiée ({length}/150 caractères)"
            if result['info']['truncated']:
                status_msg += " [Tronquée]"
            
            # Reporter dans l'historique
            detailed_message = f"SEO: Méta description générée pour '{search_data['reference']}'"
            detailed_message += f"\n==> Description: {result['description']}"
            detailed_message += f"\n==> Longueur: {length}/150 caractères"
            if result['info']['truncated']:
                detailed_message += "\n==> Description tronquée"
            
            self.main_window.user_interaction_service.add_to_history(detailed_message)
            
            # Message statusbar
            self.main_window.statusbar.showMessage(status_msg, 5000)
            
        except Exception as e:
            self.main_window.statusbar.showMessage(f"Erreur génération méta description: {e}", 3000)
            app_logger.error(f"Erreur génération méta description: {e}")
    
    def _get_current_search_data(self) -> Optional[Dict[str, any]]:
        """Extraire les données de la recherche actuelle pour la génération SEO - Logique originale"""
        try:
            # Récupérer le terme de recherche actuel
            search_term = self.main_window.search_input.text().strip()
            if not search_term:
                return None
            
            # Pour les recherches multi-références, utiliser le premier terme
            if '||' in search_term:
                terms = [term.strip() for term in search_term.split('||')]
                if terms:
                    search_term = terms[0]
            
            # Vérifier si c'est une référence de pièce (recherche dans la table pieces)
            piece_description = self._get_piece_description_from_reference(search_term)
            if not piece_description:
                return None  # Ne pas activer les boutons SEO si ce n'est pas une référence de pièce
            
            # Analyser les données du tableau pour extraire les informations des appareils
            if self.main_window.table.rowCount() == 0:
                return None
            
            # Extraire TOUS les fabricants et types depuis la base de données pour cette pièce
            # (Pas seulement ceux visibles dans le tableau)
            types_appareil = set()
            fabricants = set()
            
            # Requête pour récupérer tous les fabricants et types d'appareils pour cette pièce
            fabricants_query = Config.get_query('devices_for_piece')
            
            try:
                all_data = self.main_window.db_manager.execute_custom_query(fabricants_query, [search_term])
                for type_val, manufacturer in all_data:
                    if type_val and type_val.strip():
                        types_appareil.add(type_val.strip())
                    if manufacturer and manufacturer.strip():
                        fabricants.add(manufacturer.strip())
                        
            except Exception as e:
                app_logger.error(f"Erreur récupération fabricants pour {search_term}: {e}")
                
                # Fallback: utiliser les données visibles du tableau si la requête échoue
                for row in range(min(self.main_window.table.rowCount(), 20)):
                    if not self.main_window.table.isRowHidden(row):
                        # Type appareil (colonne 0)
                        type_item = self.main_window.table.item(row, 0)
                        if type_item and type_item.text().strip():
                            types_appareil.add(type_item.text().strip())
                        
                        # Fabricant (colonne 1)
                        fabricant_item = self.main_window.table.item(row, 1)
                        if fabricant_item and fabricant_item.text().strip():
                            fabricants.add(fabricant_item.text().strip())
            
            # Utiliser la référence de recherche et la vraie description de la pièce
            reference = search_term
            description = piece_description
            
            # Prendre le type le plus fréquent ou le premier
            type_appareil = list(types_appareil)[0] if types_appareil else "appareil électroménager"
            
            # Convertir les sets en listes
            fabricants_list = sorted(list(fabricants)) if fabricants else ["multi-marques"]
            
            return {
                'reference': reference,
                'description': description,
                'type_appareil': type_appareil,
                'fabricants': fabricants_list
            }
            
        except Exception as e:
            app_logger.error(f"Erreur extraction données recherche: {e}")
            return None
    
    def _get_search_data_from_current_data(self, reference: str, piece_description: str) -> Dict[str, any]:
        """
        Extraire les données SEO depuis current_data (plus efficace)
        """
        try:
            types = set()
            manufacturers = set()
            
            # Analyser toutes les lignes du tableau actuel
            for row_data in self.main_window.current_data:
                if len(row_data) >= 6:  # S'assurer qu'on a tous les champs
                    device_type = str(row_data[0]) if row_data[0] else ""
                    manufacturer = str(row_data[1]) if row_data[1] else ""
                    
                    # Filtrer les types qui sont des nombres
                    if device_type.strip() and not device_type.strip().isdigit():
                        types.add(device_type.strip())
                    if manufacturer.strip():
                        manufacturers.add(manufacturer.strip())
            
            return {
                'reference': reference,
                'description': piece_description,
                'types': list(types),
                'manufacturers': list(manufacturers)
            }
            
        except Exception as e:
            app_logger.error(f"Erreur extraction données depuis current_data: {e}")
            return self._get_search_data_fallback(reference, piece_description)
    
    def _get_search_data_for_existing_reference(self, reference: str, piece_description: str) -> Dict[str, any]:
        """
        Récupérer les vraies données SEO pour une référence existante en BDD
        """
        try:
            # Rechercher tous les appareils contenant cette référence de pièce
            search_results = self.main_window.db_manager.load_data(
                search_term=reference,
                limit=1000  # Limite élevée pour obtenir tous les résultats
            )
            
            if not search_results:
                return self._get_search_data_fallback(reference, piece_description)
            
            types = set()
            manufacturers = set()
            
            # Analyser tous les résultats pour extraire types et fabricants
            for result in search_results:
                if len(result) >= 6:  # S'assurer qu'on a tous les champs
                    device_type = str(result[0]) if result[0] else ""
                    manufacturer = str(result[1]) if result[1] else ""
                    
                    # Filtrer les types qui sont des nombres (comme 145008)
                    if device_type.strip() and not device_type.strip().isdigit():
                        types.add(device_type.strip())
                    if manufacturer.strip():
                        manufacturers.add(manufacturer.strip())
            
            return {
                'reference': reference,
                'description': piece_description,
                'types': list(types),
                'manufacturers': list(manufacturers)
            }
            
        except Exception as e:
            app_logger.error(f"Erreur récupération données SEO pour {reference}: {e}")
            return {
                'reference': reference,
                'description': piece_description,
                'types': [],
                'manufacturers': []
            }
    
    def _get_search_data_fallback(self, reference: str, piece_description: str) -> Dict[str, any]:
        """
        Données SEO minimales en fallback
        """
        return {
            'reference': reference,
            'description': piece_description,
            'types': [],
            'manufacturers': []
        }
    
    def _get_search_data_for_reference(self, reference: str) -> Optional[Dict[str, any]]:
        """
        Récupérer les données SEO pour une référence spécifique
        """
        try:
            # Obtenir la description de la pièce
            piece_description = self._get_piece_description_from_reference(reference)
            if not piece_description:
                return None
            
            # Récupérer les données complètes
            return self._get_search_data_for_existing_reference(reference, piece_description)
            
        except Exception as e:
            app_logger.error(f"Erreur récupération données pour référence {reference}: {e}")
            return None
    
    def _get_piece_description_from_reference(self, reference: str) -> Optional[str]:
        """
        Récupérer la description d'une pièce à partir de sa référence
        Utilise la même logique que _is_piece_reference_search()
        """
        try:
            # D'abord essayer de récupérer le libellé directement depuis la table pieces
            query = "SELECT description FROM pieces WHERE ref_piece = ? LIMIT 1"
            result = self.main_window.db_manager.execute_custom_query(query, [reference])
            
            if result:
                description = result[0][0]
                # Vérifier que la description n'est pas None ou vide
                if description and description.strip():
                    return description.strip()
                else:
                    # Si la description est vide, utiliser une description générique
                    return "pièce détachée"
            
            # Essayer une recherche partielle si la recherche exacte échoue
            query_partial = "SELECT description FROM pieces WHERE ref_piece LIKE ? LIMIT 1"
            result_partial = self.main_window.db_manager.execute_custom_query(query_partial, [f"%{reference}%"])
            
            if result_partial:
                description = result_partial[0][0]
                if description and description.strip():
                    return description.strip()
                else:
                    return "pièce détachée"
            
            return None  # Aucune pièce trouvée
                
        except Exception as e:
            app_logger.error(f"Erreur récupération description pièce: {e}")
            return None
    
    def _get_multi_reference_terms(self) -> List[str]:
        """
        Détecter si la recherche contient plusieurs références séparées par des opérateurs
        """
        try:
            search_term = self.main_window.search_input.text().strip()
            if not search_term:
                return []
            
            # Détecter les opérateurs de recherche multiple
            if '||' in search_term:
                # Opérateur OR
                terms = [term.strip() for term in search_term.split('||') if term.strip()]
                # Filtrer pour ne garder que les références de pièce valides
                valid_terms = []
                for term in terms:
                    if self._get_piece_description_from_reference(term):
                        valid_terms.append(term)
                return valid_terms if len(valid_terms) > 1 else []
            
            elif '&&' in search_term:
                # Opérateur AND - plus complexe, pour l'instant on ne traite pas
                return []
            
            # Recherche simple
            return []
            
        except Exception as e:
            app_logger.error(f"Erreur détection multi-références: {e}")
            return []
    
    def _show_reference_selection_dialog(self, title: str, message: str, default_reference: str) -> Optional[str]:
        """
        Afficher un dialogue de sélection de référence pour la génération SEO
        """
        try:
            # Récupérer toutes les références détectées
            multi_terms = self._get_multi_reference_terms()
            if not multi_terms:
                return default_reference
            
            # Utiliser QInputDialog avec une liste de choix
            reference, ok = QInputDialog.getItem(
                self.main_window,
                title,
                message,
                multi_terms,
                0,  # Index du choix par défaut
                False  # Non éditable
            )
            
            if ok and reference:
                return reference
            else:
                return None
                
        except Exception as e:
            app_logger.error(f"Erreur dialogue sélection référence: {e}")
            return default_reference
    
    def update_seo_buttons_state(self) -> None:
        """
        Mettre à jour l'état des boutons SEO selon la recherche actuelle
        """
        try:
            # Vérifier si la recherche actuelle est une référence de pièce
            search_term = self.main_window.search_input.text().strip()
            is_piece_search = False
            
            if search_term:
                # Vérifier si c'est une référence de pièce ou contient des références
                if self._get_piece_description_from_reference(search_term):
                    is_piece_search = True
                elif self._get_multi_reference_terms():
                    is_piece_search = True
            
            # Mettre à jour l'état des boutons SEO
            if hasattr(self.main_window, 'meta_title_btn'):
                self.main_window.meta_title_btn.setEnabled(is_piece_search)
            if hasattr(self.main_window, 'meta_desc_btn'):
                self.main_window.meta_desc_btn.setEnabled(is_piece_search)
                
        except Exception as e:
            app_logger.error(f"Erreur mise à jour état boutons SEO: {e}")
    
    def validate_seo_data(self, search_data: Dict[str, any]) -> bool:
        """
        Valider les données avant génération SEO
        """
        try:
            # Vérifications de base
            if not search_data:
                return False
            
            if not search_data.get('reference'):
                return False
            
            if not search_data.get('description'):
                return False
            
            # Vérifier la longueur de la référence
            if len(search_data['reference']) < 2:
                return False
            
            return True
            
        except Exception as e:
            app_logger.error(f"Erreur validation données SEO: {e}")
            return False
    
    def get_seo_stats(self) -> Dict[str, any]:
        """
        Récupérer des statistiques sur l'utilisation SEO
        """
        try:
            stats = {
                'seo_generator_available': hasattr(self, 'seo_generator') and self.seo_generator is not None,
                'current_search_valid': self._get_current_search_data() is not None,
                'multi_reference_detected': len(self._get_multi_reference_terms()) > 0
            }
            
            return stats
            
        except Exception as e:
            app_logger.error(f"Erreur récupération stats SEO: {e}")
            return {
                'seo_generator_available': False,
                'current_search_valid': False,
                'multi_reference_detected': False
            }
    
    def cleanup(self) -> None:
        """
        Nettoyer les ressources du service SEO
        """
        try:
            # Nettoyer le générateur SEO si nécessaire
            if hasattr(self.seo_generator, 'cleanup'):
                self.seo_generator.cleanup()
                
        except Exception as e:
            app_logger.error(f"Erreur nettoyage SEOService: {e}")
    
    def _format_piece_description(self, libelle: str) -> str:
        """
        Formater la description de pièce avec article et première lettre en minuscule
        Transforme 'Portillon freezer' en 'portillon freezer' avec article approprié
        
        Args:
            libelle: Le libellé brut de la pièce (ex: 'Portillon freezer')
            
        Returns:
            str: La description formatée (ex: 'portillon freezer')
        """
        try:
            if not libelle:
                return ""
            
            # Nettoyer le libellé
            clean_libelle = libelle.strip()
            if not clean_libelle:
                return ""
            
            # Mettre la première lettre en minuscule uniquement
            if len(clean_libelle) >= 1:
                formatted = clean_libelle[0].lower() + clean_libelle[1:] if len(clean_libelle) > 1 else clean_libelle.lower()
            else:
                formatted = clean_libelle
            
            return formatted
            
        except Exception as e:
            app_logger.error(f"Erreur formatage description pièce: {e}")
            return libelle  # Retourner le libellé original en cas d'erreur
    
    def _get_multi_reference_terms(self) -> List[str]:
        """Récupérer les termes de recherche multi-références"""
        try:
            search_term = self.main_window.search_input.text().strip()
            if not search_term:
                return []
            
            # Détecter les recherches multi-références avec || ou &&
            if '||' in search_term:
                terms = [term.strip() for term in search_term.split('||') if term.strip()]
                return terms if len(terms) > 1 else []
            elif '&&' in search_term:
                terms = [term.strip() for term in search_term.split('&&') if term.strip()]
                return terms if len(terms) > 1 else []
            
            return []
            
        except Exception as e:
            app_logger.error(f"Erreur récupération termes multi-références: {e}")
            return []
    
    def _show_reference_selection_dialog(self, title: str, message: str, default_reference: str) -> Optional[str]:
        """Afficher une fenêtre de sélection de référence pour les exports multi-références"""
        from .qt_imports import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
        
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.resize(450, 200)
        
        layout = QVBoxLayout()
        
        # Message d'explication
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        
        # Champ de saisie avec la référence par défaut
        reference_input = QLineEdit(default_reference)
        reference_input.selectAll()  # Sélectionner tout le texte
        layout.addWidget(reference_input)
        
        # Boutons
        button_layout = QHBoxLayout()
        
        confirm_btn = QPushButton("Confirmer")
        confirm_btn.clicked.connect(dialog.accept)
        confirm_btn.setDefault(True)
        confirm_btn.setStyleSheet("""
            QPushButton { 
                background-color: #28a745; 
                color: white; 
                font-weight: bold; 
                padding: 8px 16px; 
                border: none; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #218838; 
            }
        """)
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        cancel_btn.setStyleSheet("""
            QPushButton { 
                background-color: #6c757d; 
                color: white; 
                font-weight: bold; 
                padding: 8px 16px; 
                border: none; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #5a6268; 
            }
        """)
        
        button_layout.addWidget(confirm_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Connecter Enter pour confirmer
        reference_input.returnPressed.connect(dialog.accept)
        
        # Exécuter le dialogue
        if dialog.exec_() == QDialog.Accepted:
            selected_reference = reference_input.text().strip()
            if selected_reference:
                return selected_reference
        
        return None  # Annulé ou référence vide
    
    def _get_current_search_data_for_reference(self, specific_reference: str) -> Optional[Dict[str, any]]:
        """Extraire les données pour une référence spécifique (utilisé pour les multi-références) - Logique originale"""
        try:
            # Récupérer le terme de recherche original
            original_search_term = self.main_window.search_input.text().strip()
            
            # Si c'est une recherche multi-références, utiliser les données d'une référence existante
            if '||' in original_search_term or '&&' in original_search_term:
                # Diviser selon l'opérateur utilisé
                if '||' in original_search_term:
                    references = [ref.strip() for ref in original_search_term.split('||') if ref.strip()]
                else:  # && présent
                    references = [ref.strip() for ref in original_search_term.split('&&') if ref.strip()]
                    
                app_logger.info(f"Génération méta pour multi-références: {references}")
                
                # Essayer de trouver une référence qui existe en BDD pour récupérer les vraies données
                real_reference_data = None
                for ref in references:
                    piece_description = self._get_piece_description_from_reference(ref)
                    if piece_description:
                        app_logger.info(f"Utilisation des données de la référence existante: {ref}")
                        real_reference_data = self._get_search_data_for_existing_reference(ref, piece_description)
                        break
                
                if real_reference_data:
                    # Utiliser les vraies données mais avec la référence personnalisée
                    real_reference_data['reference'] = specific_reference
                    return real_reference_data
                else:
                    app_logger.warning("Aucune référence valide trouvée dans la recherche multi-références")
            
            # Vérifier si c'est une référence de pièce valide (cas normal)
            piece_description = self._get_piece_description_from_reference(specific_reference)
            
            # Si la référence n'existe pas en BDD, créer des données par défaut
            if not piece_description:
                return {
                    'reference': specific_reference,
                    'description': f"Pièce détachée {specific_reference}",
                    'type_appareil': "appareil électroménager", 
                    'fabricants': ["multi-marques"]
                }
            
            # Analyser les données du tableau pour extraire les informations des appareils
            if self.main_window.table.rowCount() == 0:
                return None
            
            # Extraire TOUS les fabricants et types depuis la base de données pour cette pièce
            types_appareil = set()
            fabricants = set()
            
            # Requête pour récupérer tous les fabricants et types d'appareils pour cette pièce
            fabricants_query = Config.get_query('devices_for_piece')
            
            try:
                all_data = self.main_window.db_manager.execute_custom_query(fabricants_query, [specific_reference])
                for type_val, manufacturer in all_data:
                    if type_val and type_val.strip():
                        types_appareil.add(type_val.strip())
                    if manufacturer and manufacturer.strip():
                        fabricants.add(manufacturer.strip())
                        
            except Exception as e:
                app_logger.error(f"Erreur récupération fabricants pour {specific_reference}: {e}")
                
                # Fallback: utiliser les données visibles du tableau si la requête échoue
                for row in range(min(self.main_window.table.rowCount(), 20)):
                    if not self.main_window.table.isRowHidden(row):
                        # Type appareil (colonne 0)
                        type_item = self.main_window.table.item(row, 0)
                        if type_item and type_item.text().strip():
                            types_appareil.add(type_item.text().strip())
                        
                        # Fabricant (colonne 1)
                        fabricant_item = self.main_window.table.item(row, 1)
                        if fabricant_item and fabricant_item.text().strip():
                            fabricants.add(fabricant_item.text().strip())
            
            # Prendre le type le plus fréquent ou le premier
            type_appareil = list(types_appareil)[0] if types_appareil else "appareil électroménager"
            
            # Convertir les sets en listes
            fabricants_list = sorted(list(fabricants)) if fabricants else ["multi-marques"]
            
            return {
                'reference': specific_reference,
                'description': piece_description,
                'type_appareil': type_appareil,
                'fabricants': fabricants_list
            }
            
        except Exception as e:
            app_logger.error(f"Erreur récupération données référence spécifique: {e}")
            return None
    
    def _get_search_data_for_existing_reference(self, reference: str, piece_description: str) -> Dict[str, any]:
        """Récupérer les vraies données SEO pour une référence existante en BDD"""
        try:
            # Extraire TOUS les fabricants et types depuis la base de données pour cette pièce
            types_appareil = set()
            fabricants = set()
            
            # Requête pour récupérer tous les fabricants et types d'appareils pour cette pièce
            fabricants_query = Config.get_query('devices_for_piece')
            
            try:
                all_data = self.main_window.db_manager.execute_custom_query(fabricants_query, [reference])
                for type_val, manufacturer in all_data:
                    if type_val and type_val.strip():
                        types_appareil.add(type_val.strip())
                    if manufacturer and manufacturer.strip():
                        fabricants.add(manufacturer.strip())
                        
            except Exception as e:
                app_logger.error(f"Erreur récupération fabricants pour référence existante {reference}: {e}")
            
            # Prendre le type le plus fréquent ou le premier
            type_appareil = list(types_appareil)[0] if types_appareil else "appareil électroménager"
            
            # Convertir les sets en listes
            fabricants_list = sorted(list(fabricants)) if fabricants else ["multi-marques"]
            
            return {
                'reference': reference,
                'description': piece_description,
                'type_appareil': type_appareil,
                'fabricants': fabricants_list
            }
            
        except Exception as e:
            app_logger.error(f"Erreur récupération données référence existante: {e}")
            return {
                'reference': reference,
                'description': piece_description,
                'type_appareil': "appareil électroménager", 
                'fabricants': ["multi-marques"]
            }