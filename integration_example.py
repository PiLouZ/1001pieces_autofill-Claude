#!/usr/bin/env python3
"""
Exemple d'intégration du nouveau ImportManager dans l'interface existante
Montre comment remplacer progressivement l'ancien code d'import
"""

from src.core.import_manager import ImportManager, import_files_with_dialog
from src.data.database_manager import DatabaseManager


class MainWindowWithNewImportManager:
    """
    Exemple de comment intégrer le nouveau ImportManager 
    dans l'interface principale existante
    """
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.import_manager = ImportManager(self.db_manager, parent_widget=self)
    
    # ============================================================================
    # NOUVELLES MÉTHODES - Utilisant le ImportManager factorisé
    # ============================================================================
    
    def import_files_new_way(self):
        """
        Nouvelle méthode d'import utilisant le ImportManager unifié
        Remplace: _import_file(), _import_pdf_from_path(), etc.
        """
        from PyQt5.QtWidgets import QFileDialog
        
        # Sélection des fichiers (peut être multiple)
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Importer fichiers", 
            "", 
            "Fichiers supportés (*.csv *.pdf);;Fichiers CSV (*.csv);;Fichiers PDF (*.pdf)"
        )
        
        if not file_paths:
            return
        
        # Utiliser le nouveau gestionnaire unifié
        results = self.import_manager.import_files(file_paths, show_dialog=True)
        
        if results:
            self._show_import_results_new(results)
            self._refresh_data()
    
    def import_files_quick_new_way(self, file_paths):
        """
        Import rapide sans dialogue (pour drag & drop)
        Remplace les méthodes _import_csv_from_path/_import_pdf_from_path
        """
        # Configuration par défaut basée sur les noms de fichiers
        results = self.import_manager.import_files(file_paths, show_dialog=False)
        
        if results:
            self._show_import_results_new(results)
            self._refresh_data()
    
    def _show_import_results_new(self, results):
        """Afficher les résultats d'import avec le nouveau format"""
        from PyQt5.QtWidgets import QMessageBox
        
        if results['errors']:
            error_msg = "Erreurs lors de l'import:\n" + "\n".join(results['errors'])
            QMessageBox.warning(self, "Erreurs d'import", error_msg)
        
        success_msg = f"""Import terminé avec succès !
        
📊 Résumé:
• {results['successful_files']}/{results['total_files']} fichiers traités
• {results['total_imported']} lignes importées
• {results['new_entries']} nouveaux appareils créés
• {results['matches_found']} appareils existants trouvés
• {results['associations_created']} associations pièces-appareils créées
        """
        
        QMessageBox.information(self, "Import réussi", success_msg)
    
    # ============================================================================
    # MÉTHODES DE COMPATIBILITÉ - Pour transition progressive
    # ============================================================================
    
    def _import_file(self):
        """
        Ancienne méthode - maintenant délègue vers le nouveau système
        Permet une transition en douceur
        """
        print("🔄 Redirection vers le nouveau système d'import...")
        self.import_files_new_way()
    
    def _import_pdf_from_path(self, file_paths):
        """
        Ancienne méthode PDF - maintenant délègue vers le nouveau système
        """
        print("🔄 Redirection PDF vers le nouveau système...")
        self.import_files_quick_new_way(file_paths)
    
    def _import_csv_from_path(self, file_path):
        """
        Ancienne méthode CSV - maintenant délègue vers le nouveau système
        """
        print("🔄 Redirection CSV vers le nouveau système...")
        self.import_files_quick_new_way([file_path])
    
    # ============================================================================
    # FONCTIONS UTILITAIRES
    # ============================================================================
    
    def _refresh_data(self):
        """Rafraîchir l'affichage des données"""
        print("🔄 Rafraîchissement des données...")
        # Ici on appellerait la méthode de rafraîchissement de l'interface
    
    def demonstrate_hierarchical_labels(self):
        """
        Démonstration de la nouvelle fonctionnalité de libellés hiérarchiques
        """
        print("🏷️ Démonstration des libellés hiérarchiques:")
        print()
        print("Scénario: Import de 3 fichiers PDF de pièces détachées")
        print("- resistance_chauffante.pdf")
        print("- joint_porte.pdf") 
        print("- pompe_vidange.pdf")
        print()
        print("Configuration possible:")
        print("✅ Référence commune: 'LOT_LAVE_VAISSELLE_2024'")
        print("✅ Libellé commun: 'Pièces détachées lave-vaisselle Bosch'")
        print()
        print("Résultat pour chaque appareil dans ces fichiers:")
        print("🔗 Associé à 'LOT_LAVE_VAISSELLE_2024' (libellé commun)")
        print("🔗 Associé à 'resistance_chauffante' (libellé individuel)")
        print("🔗 Associé à 'joint_porte' (libellé individuel)") 
        print("🔗 Associé à 'pompe_vidange' (libellé individuel)")
        print()
        print("➡️ Flexibilité maximale pour la recherche et l'organisation!")


def demonstrate_api_usage():
    """Démonstration de l'utilisation de l'API simplifiée"""
    print("🚀 Démonstration de l'API simplifiée du ImportManager")
    print()
    
    # Utilisation basique avec dialogue
    print("1. Import avec dialogue utilisateur:")
    print("   results = import_files_with_dialog(file_paths, db_manager, parent)")
    print()
    
    # Utilisation avancée
    print("2. Import programmatique:")
    print("   manager = ImportManager(db_manager, parent)")
    print("   results = manager.import_files(file_paths, show_dialog=False)")
    print()
    
    # Configuration avancée
    print("3. Configuration avancée:")
    print("   config = ImportConfiguration(...)")
    print("   config.use_common_reference = True")
    print("   config.common_reference = 'LOT_2024'")
    print("   config.label_config.use_common_label = True")
    print("   results = manager._execute_import(config)")


def main():
    """Démonstration principale"""
    print("🔧 Exemple d'intégration du nouveau ImportManager")
    print("=" * 60)
    print()
    
    # Démonstration de l'intégration
    window = MainWindowWithNewImportManager()
    window.demonstrate_hierarchical_labels()
    print()
    
    demonstrate_api_usage()
    print()
    
    print("🎯 Avantages de la refactorisation:")
    print("✅ Code unifié pour tous les types d'import")
    print("✅ Interface utilisateur cohérente") 
    print("✅ Support des libellés hiérarchiques")
    print("✅ Compatibilité préservée avec l'ancien code")
    print("✅ Architecture extensible pour futures fonctionnalités")
    print("✅ Tests automatisés")
    print()
    
    print("🚀 Prêt pour l'intégration dans l'application principale!")


if __name__ == "__main__":
    main()