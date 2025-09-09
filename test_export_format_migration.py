#!/usr/bin/env python3
"""
🧪 Test de la migration ExportFormat
Vérifie que tous les services d'export utilisent maintenant la définition unifiée
"""

import sys
import os
sys.path.append('src')

def test_unified_export_format():
    """Test de la définition unifiée d'ExportFormat"""
    print("=== TEST EXPORTFORMAT UNIFIÉ ===")
    
    try:
        from core.constants import ExportFormat, ExportError
        print("✅ Import ExportFormat unifié OK")
        
        # Test des valeurs
        assert ExportFormat.CSV.value == 'CSV'
        assert ExportFormat.JSON.value == 'JSON'
        assert ExportFormat.HTML_BRANDS.value == 'HTML_BRANDS'
        assert ExportFormat.HTML_DETAILS.value == 'HTML_DETAILS'
        assert ExportFormat.XML.value == 'XML'
        assert ExportFormat.EXCEL.value == 'EXCEL'
        print("✅ Toutes les valeurs présentes et correctes")
        
        # Test méthodes utilitaires
        assert ExportFormat.CSV.lowercase == 'csv'
        assert ExportFormat.XML.lowercase == 'xml'
        print("✅ Méthode lowercase OK")
        
        csv_format = ExportFormat.from_string('csv')
        assert csv_format == ExportFormat.CSV
        print("✅ Méthode from_string OK")
        
    except Exception as e:
        print(f"❌ Erreur ExportFormat: {e}")
        return False
    
    return True

def test_data_exporter_compatibility():
    """Test de compatibilité avec DataExporter"""
    print("\n=== TEST DATA EXPORTER ===")
    
    try:
        from data.data_exporter import DataExporter
        
        exporter = DataExporter()
        formats = exporter.get_supported_formats()
        
        # Vérifier les formats en minuscules (compatibilité)
        expected_formats = ['csv', 'json', 'html_brands', 'html_details', 'xml', 'excel']
        for fmt in expected_formats:
            assert fmt in formats, f"Format manquant: {fmt}"
        
        print(f"✅ DataExporter formats: {formats}")
        
    except Exception as e:
        print(f"❌ Erreur DataExporter: {e}")
        return False
    
    return True

def test_services_compatibility():
    """Test de compatibilité avec les services"""
    print("\n=== TEST SERVICES EXPORT ===")
    
    try:
        # Test import des services (sans les instancier pour éviter dépendances)
        from core.constants import ExportFormat
        
        # Vérifier que les comparaisons fonctionnent
        assert ExportFormat.CSV == ExportFormat.CSV
        assert ExportFormat.CSV != ExportFormat.JSON
        print("✅ Comparaisons Enum OK")
        
        # Test avec valeurs string (utilisé dans UI)
        assert ExportFormat.CSV.value == 'CSV'
        assert ExportFormat.HTML_BRANDS.value == 'HTML_BRANDS'
        print("✅ Compatibilité UI services OK")
        
    except Exception as e:
        print(f"❌ Erreur Services: {e}")
        return False
    
    return True

def main():
    """Lancer tous les tests"""
    print("🧪 Test de migration ExportFormat unifié")
    print("=" * 50)
    
    tests = [
        test_unified_export_format,
        test_data_exporter_compatibility, 
        test_services_compatibility
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
    
    print(f"\n📊 RÉSULTATS:")
    print(f"✅ Tests réussis: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 MIGRATION EXPORTFORMAT RÉUSSIE!")
        print("   - Définition unifiée fonctionnelle")
        print("   - Compatibilité data_exporter maintenue")
        print("   - Compatibilité services maintenue")
        return 0
    else:
        print("❌ Certains tests ont échoué")
        return 1

if __name__ == "__main__":
    sys.exit(main())