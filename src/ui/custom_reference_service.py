"""
Service de référence personnalisée - Phase 2.9
Extrait de main_refactored.py pour centraliser la logique d'export CSV personnalisé

Responsabilités:
- Export CSV avec référence personnalisée et données de recherche complexe
- Gestion des recherches multi-références (|| et && operators)
- Création de CSV de fallback minimal en cas d'erreur
- Interface standardisée pour les exports avec références customisées
"""

import csv
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.core.logger import app_logger


class CustomReferenceService:
    """
    Service spécialisé pour l'export CSV avec références personnalisées
    
    Responsabilités:
    - Export CSV avec référence custom et données complètes de recherche
    - Gestion des opérateurs de recherche multiple (|| = OR, && = AND)
    - Traitement des filtres de colonnes et de lignes incomplètes
    - Fallback vers CSV minimal en cas d'erreur
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    def export_custom_reference_csv_with_current_data(self, custom_reference: str, original_search_term: str = None) -> str:
        """
        Créer un export CSV avec toutes les données de la recherche mais avec une référence personnalisée
        
        Args:
            custom_reference: Référence personnalisée à utiliser dans la première colonne
            original_search_term: Terme de recherche original (peut contenir des opérateurs || ou &&)
            
        Returns:
            str: Message de confirmation avec le chemin du fichier créé
        """
        try:
            # Générer un nom de fichier simplifié
            filename = f"{custom_reference}_everyParts.csv"
            filepath = os.path.join(os.path.expanduser("~/Desktop"), filename)
            
            # Utiliser les données actuellement affichées dans le tableau
            # au lieu de refaire une requête en base de données
            data = self.main_window._get_displayed_table_data()
            
            if not data:
                raise Exception("Aucune donnée affichée dans le tableau à exporter")
            
            # Plus besoin de récupérer les filtres - on utilise directement les données affichées
            
            # Récupérer le filtre des lignes incomplètes si activé
            incomplete_filter = getattr(self.main_window, 'show_incomplete_only', False)
            
            # Vérifier que le db_manager existe
            if not hasattr(self.main_window, 'db_manager') or self.main_window.db_manager is None:
                raise Exception("Database manager non disponible")
            
            # Récupérer les filtres de colonnes pour l'export
            column_filters = self._get_active_column_filters()
            
            # Vérifier si c'est une recherche multi-références
            if original_search_term and ('||' in original_search_term or '&&' in original_search_term):
                data = self._handle_multi_reference_search(original_search_term, column_filters, incomplete_filter)
            else:
                # Recherche simple - utiliser les données affichées ou faire une requête
                if original_search_term:
                    data = self.main_window.db_manager.get_export_data(original_search_term, column_filters, incomplete_filter)
                # Sinon utiliser les données déjà récupérées du tableau
            
            if not data:
                raise Exception(f"Aucune donnée trouvée pour la recherche: {original_search_term}")
            
            # Créer le fichier CSV
            self._write_csv_file(filepath, custom_reference, data)
            
            return f"Fichier CSV créé: {filepath}"
            
        except Exception as e:
            app_logger.error(f"Erreur export CSV personnalisé: {e}")
            raise Exception(f"Erreur lors de l'export CSV personnalisé: {e}")
    
    def create_minimal_csv_fallback(self, custom_reference: str) -> str:
        """
        Créer un CSV minimal en cas d'erreur avec l'export personnalisé
        
        Args:
            custom_reference: Référence personnalisée à utiliser
            
        Returns:
            str: Message de confirmation avec le chemin du fichier créé
        """
        try:
            filename = f"{custom_reference}_everyParts.csv"
            filepath = os.path.join(os.path.expanduser("~/Desktop"), filename)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                
                headers = ['product', 'type', 'manufacturer', 'modele_name', 'reference_modele', 'commercial_reference']
                writer.writerow(headers)
                
                # Une seule ligne avec la référence personnalisée
                writer.writerow([
                    custom_reference,
                    'appareil électroménager',
                    'multi-marques',
                    f'Modèle compatible {custom_reference}',
                    custom_reference,
                    custom_reference
                ])
            
            return f"Fichier CSV de secours créé: {filepath}"
            
        except Exception as e:
            raise Exception(f"Erreur création CSV fallback: {e}")
    
    def _get_active_column_filters(self) -> Dict[int, str]:
        """
        Récupérer les filtres de colonnes actifs
        
        Returns:
            Dict: Mapping colonne -> filtre actif
        """
        column_filters = {}
        
        if (hasattr(self.main_window, 'table_controller') and 
            hasattr(self.main_window.table_controller, 'filter_widgets')):
            
            for col_idx, filter_widget in self.main_window.table_controller.filter_widgets.items():
                if filter_widget is not None:  # Skip removed filters
                    from PyQt5.QtWidgets import QComboBox
                    if isinstance(filter_widget, QComboBox):
                        filter_text = filter_widget.currentText().strip()
                    else:  # QLineEdit
                        filter_text = filter_widget.text().strip()
                    
                    if filter_text:
                        column_filters[col_idx] = filter_text
        
        return column_filters
    
    def _handle_multi_reference_search(self, original_search_term: str, column_filters: Dict[int, str], incomplete_filter: bool) -> List:
        """
        Gérer les recherches avec références multiples (|| ou &&)
        
        Args:
            original_search_term: Terme avec opérateurs || ou &&
            column_filters: Filtres de colonnes actifs
            incomplete_filter: Filtre des lignes incomplètes
            
        Returns:
            List: Données filtrées selon l'opérateur
        """
        if '||' in original_search_term:
            return self._handle_or_operator(original_search_term, column_filters, incomplete_filter)
        else:  # && présent
            return self._handle_and_operator(original_search_term, column_filters, incomplete_filter)
    
    def _handle_or_operator(self, search_term: str, column_filters: Dict[int, str], incomplete_filter: bool) -> List:
        """
        Gérer l'opérateur OR (||) - union de tous les résultats sans doublons
        
        Args:
            search_term: Terme avec opérateur ||
            column_filters: Filtres de colonnes
            incomplete_filter: Filtre des lignes incomplètes
            
        Returns:
            List: Données unifiées sans doublons
        """
        references = [ref.strip() for ref in search_term.split('||') if ref.strip()]
        all_data = []
        seen_records = set()
        
        for ref in references:
            ref_data = self.main_window.db_manager.get_export_data(ref, column_filters, incomplete_filter)
            if ref_data:
                for record in ref_data:
                    # Créer une clé unique pour chaque appareil (sans la référence de pièce)
                    record_key = (record[0], record[1], record[2], record[3], record[4])  # type, manufacturer, ref_modele, commercial_ref, other_ref
                    if record_key not in seen_records:
                        seen_records.add(record_key)
                        all_data.append(record)
        
        return all_data
    
    def _handle_and_operator(self, search_term: str, column_filters: Dict[int, str], incomplete_filter: bool) -> List:
        """
        Gérer l'opérateur AND (&&) - intersection des résultats
        
        Args:
            search_term: Terme avec opérateur &&
            column_filters: Filtres de colonnes
            incomplete_filter: Filtre des lignes incomplètes
            
        Returns:
            List: Données d'intersection (appareils contenant toutes les pièces)
        """
        references = [ref.strip() for ref in search_term.split('&&') if ref.strip()]
        
        if not references:
            return []
        
        # Commencer avec les données de la première référence
        first_ref = references[0]
        data = self.main_window.db_manager.get_export_data(first_ref, column_filters, incomplete_filter)
        
        # Pour chaque référence suivante, garder seulement les appareils qui la contiennent aussi
        for ref in references[1:]:
            ref_data = self.main_window.db_manager.get_export_data(ref, column_filters, incomplete_filter)
            if ref_data:
                # Créer un set des IDs d'appareils de cette référence
                ref_appareil_ids = set()
                for record in ref_data:
                    # Construire un identifiant unique pour chaque appareil
                    appareil_id = (record[0], record[1], record[2], record[3])  # type, manufacturer, ref_modele, commercial_ref
                    ref_appareil_ids.add(appareil_id)
                
                # Filtrer data pour garder seulement les appareils présents dans ref_data
                data = [record for record in data 
                       if (record[0], record[1], record[2], record[3]) in ref_appareil_ids]
            else:
                # Si une référence n'a pas de données, l'intersection est vide
                data = []
                break
        
        return data
    
    def _write_csv_file(self, filepath: str, custom_reference: str, data: List) -> None:
        """
        Écrire le fichier CSV avec les données et la référence personnalisée
        
        Args:
            filepath: Chemin du fichier à créer
            custom_reference: Référence personnalisée pour la première colonne
            data: Données à écrire dans le CSV
        """
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=';')
            
            # En-têtes
            headers = [
                'product',
                'type', 
                'manufacturer',
                'modele_name',
                'reference_modele',
                'commercial_reference'
            ]
            writer.writerow(headers)
            
            # Écrire les données en remplaçant la référence par la référence personnalisée
            for record in data:
                type_app, manufacturer, ref_modele, commercial_ref, other_ref, ref_piece = record
                modele_complet = f"{ref_modele or ''} - {commercial_ref or ''}".strip(' -')
                
                writer.writerow([
                    custom_reference,  # product (référence personnalisée au lieu de ref_piece)
                    type_app or '',
                    manufacturer or '',
                    modele_complet,
                    ref_modele or '',
                    commercial_ref or ''
                ])