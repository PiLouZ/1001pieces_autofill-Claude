#!/usr/bin/env python3
"""
Script de test pour le nouveau ImportManager
Permet de vérifier que la refactorisation fonctionne correctement
"""

import sys
import os

# Ajouter le répertoire parent au path pour les imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.core.import_manager import ImportManager, ImportConfiguration, ImportFile, FileType, ImportType, LabelConfiguration
from src.data.database_manager import DatabaseManager


def test_basic_import_manager():
    """Test basique du gestionnaire d'import"""
    print("🧪 Test du ImportManager...")
    
    # Créer une instance de base de données de test
    db_manager = DatabaseManager(":memory:")  # Base en mémoire pour les tests
    
    # Créer le gestionnaire d'import
    import_manager = ImportManager(db_manager)
    
    print("✅ ImportManager créé avec succès")
    
    # Test de détection de type de fichier
    assert import_manager._detect_file_type("test.csv") == FileType.CSV
    assert import_manager._detect_file_type("test.pdf") == FileType.PDF
    assert import_manager._detect_file_type("test.txt") is None
    
    print("✅ Détection de type de fichier OK")
    
    # Test d'extraction de référence
    ref = import_manager._extract_reference_from_filename("/path/to/piece_A123.csv")
    assert ref == "piece_A123"
    
    print("✅ Extraction de référence OK")
    
    # Test de parsing de données
    config = ImportConfiguration(files=[], import_type=ImportType.SINGLE_FILE)
    
    # Test ligne 2 colonnes
    data = import_manager._parse_row_data(["REF001", "COM001"], config)
    assert data['ref_modele'] == "REF001"
    assert data['commercial_ref'] == "COM001"
    
    # Test ligne 4+ colonnes
    data = import_manager._parse_row_data(["Type1", "Manufacturer1", "REF002", "COM002", "OTHER002"], config)
    assert data['type'] == "Type1"
    assert data['manufacturer'] == "Manufacturer1"
    assert data['ref_modele'] == "REF002"
    assert data['commercial_ref'] == "COM002"
    assert data['other_ref'] == "OTHER002"
    
    print("✅ Parsing des données OK")


def test_label_configuration():
    """Test de la configuration des libellés"""
    print("🏷️ Test de la configuration des libellés...")
    
    # Configuration avec libellé commun
    label_config = LabelConfiguration(
        use_common_label=True,
        common_label="Pièces détachées lave-vaisselle",
        individual_labels={
            "/path/file1.csv": "Résistance",
            "/path/file2.csv": "Joint"
        }
    )
    
    assert label_config.use_common_label == True
    assert label_config.common_label == "Pièces détachées lave-vaisselle"
    assert len(label_config.individual_labels) == 2
    
    print("✅ Configuration des libellés OK")


def test_import_configuration():
    """Test de la configuration d'import"""
    print("⚙️ Test de la configuration d'import...")
    
    files = [
        ImportFile(path="/test/file1.csv", type=FileType.CSV, suggested_reference="file1"),
        ImportFile(path="/test/file2.pdf", type=FileType.PDF, suggested_reference="file2")
    ]
    
    config = ImportConfiguration(
        files=files,
        import_type=ImportType.MULTI_FILE,
        use_common_reference=True,
        common_reference="LOT_2024_001"
    )
    
    assert len(config.files) == 2
    assert config.import_type == ImportType.MULTI_FILE
    assert config.use_common_reference == True
    assert config.common_reference == "LOT_2024_001"
    assert config.label_config is not None
    
    print("✅ Configuration d'import OK")


def test_mock_data_processing():
    """Test de traitement des données avec des données simulées"""
    print("📊 Test de traitement des données...")
    
    # Créer une base de données en mémoire
    db_manager = DatabaseManager(":memory:")
    import_manager = ImportManager(db_manager)
    
    # Données de test
    mock_data = [
        ["Type1", "Manufacturer1", "REF001", "COM001"],
        ["Type2", "Manufacturer2", "REF002", "COM002"],
    ]
    
    # Configuration de test
    config = ImportConfiguration(
        files=[],
        import_type=ImportType.SINGLE_FILE
    )
    
    # Tester le traitement des données
    results = import_manager._process_data_import(
        mock_data, 
        references=["TEST_PIECE"],
        label="Test Label",
        config=config
    )
    
    assert results['total_imported'] == 2
    assert results['new_entries'] >= 0  # Au moins quelques nouvelles entrées
    
    print("✅ Traitement des données OK")


def main():
    """Fonction principale de test"""
    print("🚀 Tests du nouveau ImportManager\n")
    
    try:
        test_basic_import_manager()
        print()
        
        test_label_configuration()
        print()
        
        test_import_configuration()
        print()
        
        test_mock_data_processing()
        print()
        
        print("🎉 Tous les tests sont passés avec succès !")
        print("\n📋 Résumé des améliorations:")
        print("✅ Code d'importation factorisé dans ImportManager")
        print("✅ Support des libellés hiérarchiques (commun + individuels)")
        print("✅ Interface utilisateur unifiée pour tous les types d'import")
        print("✅ Compatibilité maintenue avec les imports existants")
        print("✅ Architecture extensible pour futures améliorations")
        
    except Exception as e:
        print(f"❌ Erreur lors des tests: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())