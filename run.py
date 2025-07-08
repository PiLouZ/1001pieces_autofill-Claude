#!/usr/bin/env python3
"""
🚀 Lanceur principal - Gestionnaire d'Appareils
Point d'entrée unique pour l'application reorganisée
"""

import sys
import os

# Ajouter le répertoire src au path Python
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

def check_dependencies():
    """Vérifier les dépendances essentielles"""
    print("🔍 Vérification des dépendances...")
    
    # Vérifier Python version
    if sys.version_info < (3, 7):
        print(f"❌ Python 3.7+ requis (version actuelle: {sys.version_info.major}.{sys.version_info.minor})")
        return False
    
    # Vérifier PyQt5
    try:
        import PyQt5
        print("✅ PyQt5 disponible")
    except ImportError:
        print("❌ PyQt5 non trouvé")
        print("💡 Installez avec: pip3 install PyQt5")
        return False
    
    # Vérifier les modules locaux
    try:
        from src.core.config import Config
        from src.data.database_manager import DatabaseManager
        from src.data.data_validator import DataValidator
        from src.data.data_exporter import DataExporter
        print("✅ Modules de l'application disponibles")
    except ImportError as e:
        print(f"❌ Erreur d'import des modules: {e}")
        return False
    
    return True

def ensure_data_directory():
    """S'assurer que le répertoire data existe"""
    data_dir = os.path.join(current_dir, 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"📁 Répertoire data créé: {data_dir}")

def migrate_old_database():
    """Migrer l'ancienne base de données si elle existe"""
    old_db = os.path.join(current_dir, 'appareils.db')
    new_db = os.path.join(current_dir, 'data', 'appareils.db')
    
    if os.path.exists(old_db) and not os.path.exists(new_db):
        import shutil
        shutil.move(old_db, new_db)
        print(f"📦 Base de données déplacée vers: {new_db}")

def launch_application():
    """Lancer l'application principale"""
    print("🚀 Lancement de l'application...")
    
    try:
        # Importer et lancer l'application
        from src.ui.main_refactored import main
        main()
    except KeyboardInterrupt:
        print("\n👋 Application fermée par l'utilisateur")
        return 0
    except Exception as e:
        print(f"❌ Erreur lors du lancement: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

def main():
    """Point d'entrée principal"""
    print("🔧 Gestionnaire d'Appareils - Version Organisée")
    print("=" * 50)
    
    # Vérifications préliminaires
    if not check_dependencies():
        print("\n💥 Vérifications échouées. Installation des dépendances requise.")
        return 1
    
    # Préparation des répertoires
    ensure_data_directory()
    migrate_old_database()
    
    # Lancement
    print("\n✅ Toutes les vérifications passées")
    return launch_application()

if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        input("\nAppuyez sur Entrée pour quitter...")
    sys.exit(exit_code)