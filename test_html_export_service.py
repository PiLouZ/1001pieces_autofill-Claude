#!/usr/bin/env python3
"""
🧪 Test du service HTML Export centralisé
Vérifie que la logique HTML extraite fonctionne correctement
"""

import sys
sys.path.append('src')

def test_html_brands_generation():
    """Test de génération des liens HTML de marques"""
    print("=== TEST GÉNÉRATION LIENS MARQUES ===")
    
    try:
        from services.html_export_service import HtmlExportService
        
        # Données de test
        test_data = [
            ("produit1", "Samsung", "REF123", "COM123"),
            ("produit2", "LG", "REF456", "COM456"), 
            ("produit3", "Samsung", "REF789", "COM789"),  # Duplicate Samsung
            ("produit4", "", "REF000", "COM000"),  # Marque vide
        ]
        
        result = HtmlExportService.generate_html_brands(test_data)
        print(f"Résultat: {result}")
        
        # Vérifications
        assert 'Samsung' in result
        assert 'LG' in result
        assert '<a href="#Samsung">Samsung</a>' in result
        assert '<a href="#LG">LG</a>' in result
        # Ne devrait contenir que 2 marques (Samsung pas dupliqué, marque vide ignorée)
        assert result.count('<a href=') == 2
        
        print("✅ Génération liens marques OK")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_html_details_generation():
    """Test de génération des détails HTML"""
    print("\n=== TEST GÉNÉRATION DÉTAILS HTML ===")
    
    try:
        from services.html_export_service import HtmlExportService
        
        # Données de test plus complètes
        test_data = [
            ("produit1", "Samsung", "REF123", "COM123"),
            ("produit2", "Samsung", "REF456", "COM456"), 
            ("produit3", "LG", "REF789", "COM789"),
        ]
        
        result = HtmlExportService.generate_html_details(test_data)
        print(f"Résultat (extrait): {result[:200]}...")
        
        # Vérifications
        assert 'Samsung' in result
        assert 'LG' in result
        assert '<div id="Samsung">' in result or '<div id="LG">' in result
        assert '<b><u>' in result  # Format des en-têtes de marque
        
        print("✅ Génération détails HTML OK")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_char_counting():
    """Test du comptage de caractères non-HTML"""
    print("\n=== TEST COMPTAGE CARACTÈRES ===")
    
    try:
        from services.html_export_service import HtmlExportService
        
        # Test avec HTML simple
        html_test = '<div><b>Samsung</b> REF123 COM123</div>'
        char_count = HtmlExportService.count_non_html_chars(html_test)
        
        # Devrait compter seulement "Samsung REF123 COM123" = 21 caractères (avec espaces)
        expected_text = "Samsung REF123 COM123"
        expected_count = len(expected_text)
        
        print(f"HTML: {html_test}")
        print(f"Caractères comptés: {char_count}")
        print(f"Attendu: {expected_count}")
        
        assert char_count == expected_count
        print("✅ Comptage caractères OK")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_complete_html_export():
    """Test de l'export HTML complet"""
    print("\n=== TEST EXPORT HTML COMPLET ===")
    
    try:
        from services.html_export_service import HtmlExportService
        
        # Données de test
        test_data = [
            ("produit1", "Samsung", "REF123", "COM123"),
            ("produit2", "LG", "REF456", "COM456"), 
        ]
        
        result = HtmlExportService.generate_complete_html_export(test_data, "TEST_SEARCH")
        
        # Vérifications
        assert 'TEST_SEARCH' in result  # Terme de recherche dans titre
        assert 'brands-navigation' in result  # Section navigation
        assert 'details-content' in result  # Section détails
        assert 'Samsung' in result and 'LG' in result  # Les deux marques
        
        print("✅ Export HTML complet OK")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    """Lancer tous les tests"""
    print("🧪 Test du service HTML Export centralisé")
    print("=" * 50)
    
    tests = [
        test_html_brands_generation,
        test_html_details_generation,
        test_char_counting,
        test_complete_html_export
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
    
    print(f"\n📊 RÉSULTATS:")
    print(f"✅ Tests réussis: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 SERVICE HTML EXPORT FONCTIONNEL!")
        print("   - Génération liens marques: OK")
        print("   - Génération détails HTML: OK") 
        print("   - Comptage caractères: OK")
        print("   - Export HTML complet: OK")
        print("\n✨ Prêt pour remplacer les 200+ lignes dupliquées!")
        return 0
    else:
        print("❌ Certains tests ont échoué")
        return 1

if __name__ == "__main__":
    sys.exit(main())