"""
Paste Results Service - Phase 2.16
Service dédié à la gestion des résultats de collage

Responsabilités:
- Affichage des résumés de collage
- Logging des résultats dans l'historique
- Formatage des statistiques de collage
"""

from typing import Optional
from ..ui.qt_imports import QMessageBox
from ..core.logger import app_logger
from ..utils.error_handler import handle_paste_results_errors

class PasteResultsService:
    """
    Service de gestion des résultats de collage
    
    Responsabilités:
    - Formatage et affichage des résumés de collage
    - Logging des résultats dans l'historique utilisateur
    - Présentation des statistiques de manière claire
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    @handle_paste_results_errors()
    def show_paste_summary(self, inserted_count: int, updated_count: int, ignored_count: int,
                          associations_created: int, duplicates_skipped: int,
                          manual_completion_count: int, descriptions_updated: int,
                          total_rows: int) -> None:
        """
        Afficher un résumé du collage dans une boîte de dialogue
        
        Args:
            inserted_count: Nombre de nouveaux appareils créés
            updated_count: Nombre d'appareils mis à jour
            ignored_count: Nombre de lignes ignorées
            associations_created: Nombre d'associations créées
            duplicates_skipped: Nombre de doublons ignorés
            manual_completion_count: Nombre d'appareils nécessitant completion manuelle
            descriptions_updated: Nombre de descriptions mises à jour
            total_rows: Nombre total de lignes traitées
        """
        # Créer un résumé détaillé pour l'affichage
        summary_lines = [f"📥 **Résumé du collage** ({total_rows} lignes traitées)", ""]

        if inserted_count > 0:
            summary_lines.append(f"✅ **Nouveaux appareils créés**: {inserted_count}")
        if updated_count > 0:
            summary_lines.append(f"🔄 **Appareils mis à jour**: {updated_count}")
        if associations_created > 0:
            summary_lines.append(f"🔗 **Associations créées**: {associations_created}")
        if descriptions_updated > 0:
            summary_lines.append(f"📝 **Descriptions mises à jour**: {descriptions_updated}")
        if duplicates_skipped > 0:
            summary_lines.append(f"⚠️ **Doublons ignorés**: {duplicates_skipped}")
        if manual_completion_count > 0:
            summary_lines.append(f"✋ **Nécessitent complétion manuelle**: {manual_completion_count}")
        if ignored_count > 0:
            summary_lines.append(f"❌ **Lignes ignorées**: {ignored_count}")

        if inserted_count == 0 and updated_count == 0 and associations_created == 0:
            summary_lines.append("ℹ️ **Aucune modification apportée**")

        summary_text = "\n".join(summary_lines)

        # Afficher le résumé dans une boîte de message
        msg = QMessageBox(self.main_window)
        msg.setWindowTitle("Résumé du collage")
        msg.setText(summary_text)
        msg.setIcon(QMessageBox.Information)
        msg.exec_()
    
    @handle_paste_results_errors()
    def log_paste_results(self, inserted_count: int, updated_count: int, ignored_count: int,
                         associations_created: int, duplicates_skipped: int,
                         manual_completion_count: int, descriptions_updated: int,
                         total_rows: int, ref_piece: str) -> None:
        """
        Logger les résultats du collage dans l'historique
        
        Args:
            inserted_count: Nombre de nouveaux appareils créés
            updated_count: Nombre d'appareils mis à jour
            ignored_count: Nombre de lignes ignorées
            associations_created: Nombre d'associations créées
            duplicates_skipped: Nombre de doublons ignorés
            manual_completion_count: Nombre d'appareils nécessitant completion manuelle
            descriptions_updated: Nombre de descriptions mises à jour
            total_rows: Nombre total de lignes traitées
            ref_piece: Référence de la pièce
        """
        # Créer un résumé concis pour l'historique
        summary_parts = []

        if inserted_count > 0:
            summary_parts.append(f"{inserted_count} nouvel(s) appareil(s)")
        if updated_count > 0:
            summary_parts.append(f"{updated_count} mis à jour")
        if associations_created > 0:
            summary_parts.append(f"{associations_created} association(s)")
        if descriptions_updated > 0:
            summary_parts.append(f"{descriptions_updated} description(s) mises à jour")
        if duplicates_skipped > 0:
            summary_parts.append(f"{duplicates_skipped} doublon(s) ignoré(s)")
        if manual_completion_count > 0:
            summary_parts.append(f"{manual_completion_count} nécessite(nt) complétion")

        if summary_parts:
            summary = f"📥 Collage '{ref_piece}': {', '.join(summary_parts)} ({total_rows} lignes traitées)"
        else:
            summary = f"📥 Collage '{ref_piece}': {total_rows} lignes traitées (aucune modification)"

        # Ajouter à l'historique
        if hasattr(self.main_window, 'user_interaction_service'):
            self.main_window.user_interaction_service.add_to_history(summary)
    
    def format_paste_statistics(self, inserted_count: int, updated_count: int, ignored_count: int,
                               associations_created: int, duplicates_skipped: int, 
                               manual_completion_count: int, descriptions_updated: int,
                               total_rows: int) -> str:
        """
        Formater les statistiques de collage pour affichage console/debug
        
        Returns:
            str: Statistiques formatées
        """
        stats = []
        stats.append(f"Total: {total_rows} lignes")
        stats.append(f"Créés: {inserted_count}")
        stats.append(f"Mis à jour: {updated_count}")
        stats.append(f"Associations: {associations_created}")
        stats.append(f"Descriptions: {descriptions_updated}")
        stats.append(f"Ignorés: {ignored_count}")
        stats.append(f"Doublons: {duplicates_skipped}")
        stats.append(f"Complétion req.: {manual_completion_count}")
        
        return " | ".join(stats)