"""
📚 Exemples d'utilisation des modules refactorisés
Démontre comment utiliser les nouveaux helpers centralisés
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from core.constants import Messages, UIConfig, FileExtensions, ValidationRules
from utils.error_handler import handle_errors, SafeOperation, ErrorReporter

# Note: PyQt5 non installé dans cet environnement, donc les imports Qt sont commentés
# from ui.qt_imports import *
# from ui.message_helper import MessageHelper, CommonMessages
# from ui.dialog_manager import DialogManager


class ExampleService:
    """Exemple d'utilisation des modules refactorisés"""
    
    def __init__(self, parent=None):
        self.parent = parent
    
    @handle_errors(title="Erreur de traitement", return_on_error=None)
    def process_data_with_decorator(self, data):
        """Exemple d'utilisation du décorateur de gestion d'erreurs"""
        if not data:
            raise ValueError("Données vides")
        
        # Simulation d'un traitement qui peut lever une exception
        if data == "error":
            raise RuntimeError("Erreur simulée")
        
        return f"Données traitées: {data}"
    
    def process_data_with_context_manager(self, data):
        """Exemple d'utilisation du context manager SafeOperation"""
        with SafeOperation(self.parent, "Erreur de traitement") as safe:
            if not data:
                raise ValueError("Données vides")
            
            result = f"Données traitées: {data}"
            safe.set_result(result)
        
        if safe.success:
            return safe.result
        else:
            return None
    
    def process_multiple_items(self, items):
        """Exemple d'utilisation de ErrorReporter pour traitement en lot"""
        reporter = ErrorReporter(self.parent)
        
        results = []
        for item in items:
            result = reporter.run_operation(
                self._process_single_item, 
                f"Traitement de {item}",
                item
            )
            if result:
                results.append(result)
        
        # Afficher le résumé (nécessiterait PyQt5 installé)
        # reporter.show_summary("Traitement terminé")
        
        print(reporter.get_summary())
        return results
    
    def _process_single_item(self, item):
        """Traite un seul élément (peut lever des exceptions)"""
        if item == "error":
            raise ValueError(f"Erreur sur {item}")
        return f"Traité: {item}"


def demonstrate_constants():
    """Démonstration de l'utilisation des constantes centralisées"""
    print("=== DÉMONSTRATION CONSTANTES ===")
    print(f"Message de succès: {Messages.SAVE_SUCCESS}")
    print(f"Couleur de succès: {UIConfig.COLOR_SUCCESS}")
    print(f"Extension CSV: {FileExtensions.CSV_EXPORT}")
    print(f"Longueur max référence: {ValidationRules.MAX_REFERENCE_LENGTH}")
    print()


def demonstrate_error_handling():
    """Démonstration de la gestion d'erreurs"""
    print("=== DÉMONSTRATION GESTION D'ERREURS ===")
    
    service = ExampleService()
    
    print("1. Test décorateur avec succès:")
    result = service.process_data_with_decorator("données_valides")
    print(f"   Résultat: {result}")
    
    print("\n2. Test décorateur avec erreur:")
    result = service.process_data_with_decorator("error")
    print(f"   Résultat: {result}")
    
    print("\n3. Test context manager avec succès:")
    result = service.process_data_with_context_manager("données_valides")
    print(f"   Résultat: {result}")
    
    print("\n4. Test traitement en lot:")
    items = ["item1", "item2", "error", "item3", "error2"]
    results = service.process_multiple_items(items)
    print(f"   Résultats valides: {len(results)}")
    print()


def demonstrate_file_extensions():
    """Démonstration de l'utilisation des extensions de fichiers"""
    print("=== DÉMONSTRATION EXTENSIONS FICHIERS ===")
    
    reference = "TEST_REF"
    
    # Avant refactorisation (hardcodé):
    # old_filename = f"{reference}_everyParts.csv"
    
    # Après refactorisation (centralisé):
    new_filename = f"{reference}{FileExtensions.CSV_EXPORT}"
    
    print(f"Nom de fichier généré: {new_filename}")
    print(f"Extensions d'import supportées: {FileExtensions.IMPORT_EXTENSIONS}")
    print()


# Exemple de code migré
class OldStyleClass:
    """Exemple de classe AVANT refactorisation"""
    
    def old_save_method(self):
        """Méthode avec gestion d'erreur dupliquée (AVANT)"""
        try:
            # Simulation de sauvegarde
            if False:  # Simulation d'erreur
                raise Exception("Erreur de sauvegarde")
            print("Sauvegarde réussie")
        except Exception as e:
            # Code dupliqué dans tout le projet (295 fois!)
            print(f"❌ Erreur: {e}")
            # QMessageBox.critical(self, "Erreur", f"Erreur: {e}")


class NewStyleClass:
    """Exemple de classe APRÈS refactorisation"""
    
    @handle_errors(title="Erreur de sauvegarde")
    def new_save_method(self):
        """Méthode avec gestion d'erreur centralisée (APRÈS)"""
        # Simulation de sauvegarde
        if False:  # Simulation d'erreur
            raise Exception("Erreur de sauvegarde")
        print("✅ Sauvegarde réussie")


def demonstrate_migration():
    """Démonstration de la migration du code"""
    print("=== DÉMONSTRATION MIGRATION CODE ===")
    
    print("Style ancien (gestion d'erreur dupliquée):")
    old_class = OldStyleClass()
    old_class.old_save_method()
    
    print("\nStyle nouveau (gestion d'erreur centralisée):")
    new_class = NewStyleClass()
    new_class.new_save_method()
    print()


if __name__ == "__main__":
    print("🚀 EXEMPLES DE REFACTORISATION - 1001pieces")
    print("=" * 50)
    
    demonstrate_constants()
    demonstrate_error_handling()
    demonstrate_file_extensions()
    demonstrate_migration()
    
    print("✅ Tous les exemples ont été exécutés avec succès!")
    print("\n📊 IMPACT DE LA REFACTORISATION:")
    print("• 29 fichiers avec imports PyQt5 → 1 module centralisé")
    print("• 39 QMessageBox dupliqués → MessageHelper unifié") 
    print("• 295 blocs try/catch → Décorateurs centralisés")
    print("• 2 DialogService en conflit → DialogManager unifié")
    print("• 50+ constantes hardcodées → Module constants centralisé")