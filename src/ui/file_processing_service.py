"""
Service de traitement des fichiers - Phase 2.7
Extrait de main_refactored.py pour centraliser la logique de traitement des fichiers

Responsabilités:
- Traitement des imports PDF avec progress tracking
- Gestion des fallbacks ImportManager vers système legacy
- Validation et extraction des données de fichiers
- Interface standardisée pour le traitement de fichiers
"""

import os
from typing import List, Optional, Dict, Any, Tuple
from .qt_imports import QProgressDialog, QApplication, Qt
from src.core.logger import app_logger


class FileProcessingService:
    """
    Service spécialisé pour le traitement des fichiers et imports
    
    Responsabilités:
    - Import PDF avec gestion des erreurs et progress
    - Fallback automatique vers système legacy
    - Validation des fichiers et extraction des données
    - Intégration avec ImportManager
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        # L'import_manager sera accessible via self.main_window.import_manager quand nécessaire
        
    def import_pdf_files(self, file_paths: List[str]) -> bool:
        """
        Importer un ou plusieurs fichiers PDF depuis des chemins donnés
        
        Args:
            file_paths: Liste des chemins des fichiers PDF à traiter
            
        Returns:
            bool: True si l'import a réussi, False sinon
        """
        try:
            # Assurer que file_paths est une liste
            if isinstance(file_paths, str):
                file_paths = [file_paths]
            
            # PHASE 2.2 OPTIMISATION: Utiliser callback pour dialogue non-bloquant
            self.main_window.import_manager.import_from_drag_drop(
                file_paths,
                callback=self.main_window._on_import_complete
            )
            return True  # Retour immédiat, résultat via callback
        except Exception as e:
            app_logger.warning(f"Échec ImportManager drag&drop PDF, fallback vers ancien système: {e}")
        
        # FALLBACK : Code legacy en cas d'échec ImportManager
        return self._import_pdf_legacy(file_paths)
    
    def _import_pdf_legacy(self, file_paths: List[str]) -> bool:
        """
        Import PDF avec le système legacy (fallback)
        
        Args:
            file_paths: Liste des chemins des fichiers PDF
            
        Returns:
            bool: True si l'import a réussi, False sinon
        """
        try:
            from src.data.pdf_extractor_camelot import CamelotPDFExtractor, PDFExtractionError
            
            # Extraire le nom du fichier pour la référence de pièce (si un seul fichier)
            suggested_ref_piece = None
            if len(file_paths) == 1:
                suggested_ref_piece = os.path.splitext(os.path.basename(file_paths[0]))[0]
            
            # Obtenir l'aperçu des données PDF
            sample_data = self._get_pdf_sample_data(file_paths[0] if file_paths else None)
            
            # Afficher la boîte de dialogue d'options d'import avec aperçu
            import_options = self.main_window._get_import_options_unified(
                detected_columns=3,
                default_ref_piece=suggested_ref_piece,
                import_method="PDF",
                sample_data=sample_data
            )
            if not import_options:
                return False
                
            import_type, ref_piece, third_column_choice, has_headers, libelle_piece = import_options
            
            # Traiter les fichiers PDF
            processing_result = self._process_pdf_files(file_paths, third_column_choice)
            if not processing_result:
                return False
                
            all_converted_data, processed_files, pdf_files_info = processing_result
            
            # Traiter l'import avec la même logique que CSV
            lines_progress = self._create_lines_progress_dialog(len(all_converted_data))
            results = self.main_window._process_import(
                all_converted_data, import_type, ref_piece, 
                third_column_choice, lines_progress, libelle_piece
            )
            
            if lines_progress:
                lines_progress.setValue(len(all_converted_data))
                lines_progress.close()
            
            # Finaliser l'import
            self._finalize_pdf_import(results, ref_piece, processed_files, pdf_files_info)
            return True
            
        except Exception as e:
            self.main_window._show_error(f"Erreur lors de l'import PDF: {e}")
            app_logger.error(f"Erreur import PDF legacy: {e}")
            return False
    
    def _get_pdf_sample_data(self, pdf_path: Optional[str]) -> List[Any]:
        """
        Obtenir un aperçu des données PDF pour la dialogue d'options

        Args:
            pdf_path: Chemin du fichier PDF

        Returns:
            List: Données d'aperçu ou liste vide en cas d'erreur
        """
        if not pdf_path:
            return []

        try:
            return self.main_window.import_manager.load_pdf_data(pdf_path, max_rows=3)
        except Exception as e:
            app_logger.warning(f"Impossible d'obtenir l'aperçu PDF, dialogue sans aperçu: {e}")
            return []
    
    def _process_pdf_files(self, file_paths: List[str], third_column_choice: str) -> Optional[Tuple[List, List, List]]:
        """
        Traiter tous les fichiers PDF et extraire les données
        
        Args:
            file_paths: Liste des chemins des fichiers
            third_column_choice: Choix pour la troisième colonne ("notes", "other_ref", "ignore")
            
        Returns:
            Tuple contenant (données_converties, fichiers_traités, infos_fichiers) ou None
        """
        try:
            from src.data.pdf_extractor_camelot import CamelotPDFExtractor, PDFExtractionError
            
            # Créer l'extracteur Camelot
            extractor = CamelotPDFExtractor()
            
            # Initialiser les containers de résultats
            all_converted_data = []
            processed_files = []
            pdf_files_info = []
            
            # Créer une barre de progression pour l'import PDF
            total_files = len(file_paths)
            progress_dialog = self._create_file_progress_dialog(total_files)
            progress_dialog.show()
            QApplication.processEvents()
            
            for file_idx, file_path in enumerate(file_paths):
                # Vérifier l'annulation
                if progress_dialog.wasCanceled():
                    break
                
                # Mettre à jour la progression
                progress_dialog.setValue(file_idx)
                progress_dialog.setLabelText(f"Traitement: {os.path.basename(file_path)} ({file_idx + 1} / {total_files})")
                QApplication.processEvents()
                
                # Traiter le fichier individuel
                file_result = self._process_single_pdf_file(extractor, file_path, third_column_choice)
                if file_result:
                    converted_data, file_info = file_result
                    all_converted_data.extend(converted_data)
                    processed_files.append(os.path.basename(file_path))
                    pdf_files_info.append(file_info)
            
            # Fermer la barre de progression
            progress_dialog.setValue(total_files)
            progress_dialog.close()
            
            if not all_converted_data:
                self.main_window._show_error("Aucune donnée extraite des fichiers PDF")
                return None
            
            print(f"📊 Total des lignes converties pour traitement: {len(all_converted_data)}")
            return all_converted_data, processed_files, pdf_files_info
            
        except Exception as e:
            app_logger.error(f"Erreur traitement fichiers PDF: {e}")
            self.main_window._show_error(f"Erreur lors du traitement des fichiers PDF: {e}")
            return None
    
    def _process_single_pdf_file(self, extractor, file_path: str, third_column_choice: str) -> Optional[Tuple[List, Dict]]:
        """
        Traiter un seul fichier PDF
        
        Args:
            extractor: Instance de CamelotPDFExtractor
            file_path: Chemin du fichier PDF
            third_column_choice: Choix pour la troisième colonne
            
        Returns:
            Tuple contenant (données_converties, infos_fichier) ou None
        """
        try:
            # Valider la compatibilité
            is_compatible, error_msg = extractor.validate_pdf_compatibility(file_path)
            if not is_compatible:
                self.main_window._show_error(f"PDF non compatible ({os.path.basename(file_path)}): {error_msg}")
                return None
            
            # Extraire les données
            extracted_data = extractor.extract_data(file_path)
            if not extracted_data:
                self.main_window._show_error(f"Aucune donnée extraite du fichier PDF: {os.path.basename(file_path)}")
                return None
            
            # Préparer les informations du fichier
            file_info = {
                'filename': os.path.basename(file_path),
                'lines_extracted': len(extracted_data)
            }
            
            # Convertir les données selon le choix de la troisième colonne
            converted_data = []
            for row in extracted_data:
                if third_column_choice == "notes":
                    converted_data.append([row[0], row[1], row[2]])  # [ref_modele, commercial_ref, notes]
                elif third_column_choice == "other_ref":
                    converted_data.append([row[0], row[1], row[2]])  # [ref_modele, commercial_ref, other_ref]
                else:  # ignore
                    converted_data.append([row[0], row[1], ""])  # [ref_modele, commercial_ref, ignored]
            
            return converted_data, file_info
            
        except Exception as e:
            self.main_window._show_error(f"Erreur lors du traitement de {os.path.basename(file_path)}: {e}")
            app_logger.error(f"Erreur traitement fichier PDF {file_path}: {e}")
            return None
    
    def _create_file_progress_dialog(self, total_files: int) -> QProgressDialog:
        """
        Créer une barre de progression pour le traitement des fichiers
        
        Args:
            total_files: Nombre total de fichiers à traiter
            
        Returns:
            QProgressDialog configuré
        """
        progress_dialog = self.main_window._create_progress_dialog(
            "Import PDF", 
            total_files, 
            "Import PDF en cours... {} / {} fichier(s)"
        )
        return progress_dialog
    
    def _create_lines_progress_dialog(self, total_lines: int) -> Optional[QProgressDialog]:
        """
        Créer une barre de progression pour le traitement des lignes (si nécessaire)
        
        Args:
            total_lines: Nombre total de lignes à traiter
            
        Returns:
            QProgressDialog ou None si pas nécessaire
        """
        if total_lines < 1000:  # Seulement pour les gros imports
            return None
            
        lines_progress = QProgressDialog(
            f"Traitement des lignes... 0 / {total_lines}",
            "Annuler",
            0, total_lines,
            self.main_window
        )
        lines_progress.setWindowTitle("Traitement des données")
        lines_progress.setWindowModality(Qt.WindowModality.WindowModal)
        lines_progress.show()
        QApplication.processEvents()
        
        return lines_progress
    
    def _finalize_pdf_import(self, results: Dict[str, Any], ref_piece: str, 
                           processed_files: List[str], pdf_files_info: List[Dict]) -> None:
        """
        Finaliser l'import PDF : historique et affichage
        
        Args:
            results: Résultats du traitement d'import
            ref_piece: Référence de pièce utilisée
            processed_files: Liste des fichiers traités avec succès
            pdf_files_info: Informations détaillées des fichiers PDF
        """
        # Enregistrer dans l'historique
        if len(processed_files) == 1:
            source_info = f"PDF ({processed_files[0]})"
        else:
            source_info = f"PDF ({len(processed_files)} fichiers)"
        
        self.main_window._log_import_to_history(results, ref_piece, source_info, pdf_files_info)
        
        # Actualiser l'affichage
        self.main_window._force_refresh_display(reset_page=True, clear_filters=True)