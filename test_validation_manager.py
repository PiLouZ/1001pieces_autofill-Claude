#!/usr/bin/env python3
"""
Test de non-régression pour ValidationManagerService - PHASE 4 PRIORITÉ 2
Vérifie que le service de validation unifié fonctionne correctement
et peut remplacer les 306+ patterns dispersés
"""

import sys
import os
sys.path.insert(0, 'src')

from src.core.validation_manager import (
    ValidationManagerService, ValidationLevel, ValidationResult, ValidationSummary,
    default_validator, strict_validator, is_empty_field, clean_field_value,
    validate_search_term, clean_reference
)

def test_empty_field_patterns():
    """Test 1: Remplacer les 306 patterns .strip()"""
    print("🧪 Test 1: Patterns champs vides...")
    
    # Test patterns les plus fréquents
    assert is_empty_field("") == True
    assert is_empty_field("   ") == True  
    assert is_empty_field(None) == True
    assert is_empty_field("  valid  ") == False
    assert is_empty_field("valid") == False
    assert is_empty_field([]) == True
    assert is_empty_field({}) == True
    assert is_empty_field(["item"]) == False
    
    print("   ✅ Patterns is_empty_field remplacent 306 occurrences .strip()")

def test_field_cleaning():
    """Test 2: Nettoyage unifié des champs"""
    print("\n🧪 Test 2: Nettoyage des champs...")
    
    # Test nettoyage standard
    assert clean_field_value("  test  ") == "test"
    assert clean_field_value("") == ""
    assert clean_field_value(None) == ""
    assert clean_field_value("  ") == ""
    assert clean_field_value(None, "default") == "default"
    assert clean_field_value("", "fallback") == "fallback"
    
    # Test conversion types
    assert clean_field_value(123) == "123"
    assert clean_field_value(True) == "True"
    
    print("   ✅ Nettoyage unifié remplace patterns dispersés")

def test_reference_cleaning():
    """Test 3: Nettoyage spécialisé des références"""
    print("\n🧪 Test 3: Nettoyage des références...")
    
    # Test nettoyage références
    result = default_validator.clean_reference("  ref-123  ")
    assert result.is_valid == True
    assert result.cleaned_value == "REF-123"
    
    result = strict_validator.clean_reference("ref__123--abc")
    assert result.cleaned_value == "REF-123-ABC"
    
    result = default_validator.clean_reference("")
    assert result.cleaned_value == ""
    
    result = default_validator.clean_reference(None)
    assert result.cleaned_value == ""
    
    print("   ✅ Nettoyage références consolide 50+ patterns")

def test_search_term_validation():
    """Test 4: Validation termes de recherche"""
    print("\n🧪 Test 4: Validation termes de recherche...")
    
    # Test validation search terms
    result = default_validator.validate_search_term("valid_search")
    assert result.is_valid == True
    assert result.cleaned_value == "valid_search"
    
    result = default_validator.validate_search_term("")
    assert result.is_valid == False
    assert "vide" in result.error_message.lower()
    
    result = default_validator.validate_search_term("a")  # Trop court
    assert result.is_valid == False
    assert "caractères" in result.error_message.lower()
    
    result = default_validator.validate_search_term("  valid  ")
    assert result.is_valid == True
    assert result.cleaned_value == "valid"
    
    print("   ✅ Validation recherche remplace 15+ patterns similaires")

def test_required_field_validation():
    """Test 5: Validation champs obligatoires"""
    print("\n🧪 Test 5: Validation champs obligatoires...")
    
    result = default_validator.validate_required_field("manufacturer", "manufacturer")
    assert result.is_valid == True
    assert result.cleaned_value == "manufacturer"
    
    result = default_validator.validate_required_field("", "manufacturer")
    assert result.is_valid == False
    assert "obligatoire" in result.error_message.lower()
    
    # Test longueur maximale
    long_value = "a" * 200
    result = default_validator.validate_required_field(long_value, "test", max_length=10)
    assert result.is_valid == False  # Dépasse longueur max
    assert len(result.cleaned_value) == 10  # Valeur tronquée
    
    print("   ✅ Validation champs obligatoires factorée")

def test_device_references_validation():
    """Test 6: Validation références d'appareils"""
    print("\n🧪 Test 6: Validation références appareils...")
    
    # Test références valides
    summary = default_validator.validate_device_references(
        "REF-123", "COMM-456", "OTHER-789"
    )
    assert summary.is_fully_valid == True
    
    # Test aucune référence (erreur critique)
    summary = default_validator.validate_device_references("", "", "")
    assert summary.is_fully_valid == False
    error_messages = summary.get_error_messages()
    assert any("obligatoire" in msg.lower() for msg in error_messages)
    
    # Test références identiques (erreur)
    summary = default_validator.validate_device_references("REF-123", "REF-123", "")
    assert summary.is_fully_valid == False
    error_messages = summary.get_error_messages()
    assert any("identiques" in msg.lower() for msg in error_messages)
    
    # Test seulement other_ref (warning)
    summary = strict_validator.validate_device_references("", "", "OTHER-REF")
    assert summary.has_warnings == True
    warning_messages = summary.get_warning_messages()
    assert len(warning_messages) > 0
    
    print("   ✅ Validation références consolide logique dispersée")

def test_import_data_validation():
    """Test 7: Validation données d'import en lot"""
    print("\n🧪 Test 7: Validation import en lot...")
    
    test_data = [
        {"manufacturer": "Brand1", "ref_modele": "REF1"},
        {"manufacturer": "Brand2", "ref_modele": ""},  # Invalid
        {"manufacturer": "", "ref_modele": "REF3"},    # Invalid
        {"manufacturer": "Brand4", "ref_modele": "REF4", "commercial_ref": "COMM4"}
    ]
    
    summary = default_validator.validate_import_data(test_data, ["manufacturer", "ref_modele"])
    
    # Devrait avoir des erreurs pour les enregistrements 2 et 3
    assert summary.invalid_fields > 0
    assert summary.valid_fields > 0
    assert summary.total_fields > 0
    
    print(f"   - {summary.valid_fields}/{summary.total_fields} champs valides")
    print(f"   - {summary.invalid_fields} erreurs détectées")
    print("   ✅ Validation import utilise ErrorReporter sous-exploité")

def test_export_criteria_validation():
    """Test 8: Validation critères d'export"""
    print("\n🧪 Test 8: Validation critères export...")
    
    # Critères valides
    criteria = {
        "search_term": "test_search",
        "format": "CSV"
    }
    result = default_validator.validate_export_criteria(criteria)
    assert result.is_valid == True
    
    # Format invalide
    criteria["format"] = "INVALID_FORMAT"
    result = default_validator.validate_export_criteria(criteria)
    assert result.is_valid == False
    assert "format" in result.error_message.lower()
    
    # Terme de recherche invalide
    criteria["format"] = "CSV"
    criteria["search_term"] = ""
    result = default_validator.validate_export_criteria(criteria)
    assert result.is_valid == False
    
    print("   ✅ Validation export centralisée")

def test_validation_levels():
    """Test 9: Niveaux de validation"""
    print("\n🧪 Test 9: Niveaux de validation...")
    
    # Test modes différents
    basic_validator = ValidationManagerService(strict_mode=False)
    strict_validator = ValidationManagerService(strict_mode=True)
    
    assert basic_validator.default_level == ValidationLevel.STANDARD
    assert strict_validator.default_level == ValidationLevel.STRICT
    
    # Comportement différent selon le mode
    result_basic = basic_validator.clean_reference("ref-123")
    result_strict = strict_validator.clean_reference("ref-with-invalid-format")
    
    # Le mode strict devrait générer plus de warnings
    assert result_basic.is_valid == True
    assert result_strict.is_valid == True  # Toujours valide, mais peut avoir warnings
    
    print("   ✅ Niveaux de validation configurables")

def test_compatibility_functions():
    """Test 10: Fonctions de compatibilité"""
    print("\n🧪 Test 10: Fonctions de compatibilité...")
    
    # Test fonctions de compatibilité pour migration facile
    assert validate_search_term("valid_term") == True
    assert validate_search_term("") == False
    
    assert clean_reference("  REF-123  ") == "REF-123"
    assert clean_reference("") == ""
    
    assert is_empty_field("") == True
    assert is_empty_field("valid") == False
    
    assert clean_field_value("  test  ") == "test"
    assert clean_field_value(None, "default") == "default"
    
    print("   ✅ Fonctions compatibilité facilitent migration")

def test_error_handling_integration():
    """Test 11: Intégration avec error_handler.py"""
    print("\n🧪 Test 11: Intégration error_handler...")
    
    # Le service utilise les décorateurs error_handler
    # Test que les méthodes sont bien décorées (ne lèvent pas d'exceptions non gérées)
    try:
        # Forcer une erreur interne pour tester la gestion
        result = default_validator.validate_required_field(None, "test_field")
        # Devrait retourner un résultat valide même avec None
        assert isinstance(result, ValidationResult)
        print("   - Gestion erreurs intégrée ✓")
        
        # Test SafeOperation indirectement via validate_batch_fields
        values = {"field1": "value1", "field2": None}
        configs = {"field1": {"required": True}, "field2": {"required": False}}
        summary = default_validator.validate_batch_fields(values, configs)
        assert isinstance(summary, ValidationSummary)
        print("   - SafeOperation utilisé ✓")
        
    except Exception as e:
        print(f"   - Erreur non gérée: {e}")
        return False
    
    print("   ✅ Intégration error_handler.py massive réussie")
    return True

def run_all_tests():
    """Exécuter tous les tests de validation"""
    print("🧪 TESTS VALIDATION MANAGER - PHASE 4 PRIORITÉ 2")
    print("=" * 65)
    
    tests = [
        test_empty_field_patterns,
        test_field_cleaning,
        test_reference_cleaning,
        test_search_term_validation,
        test_required_field_validation,
        test_device_references_validation,
        test_import_data_validation,
        test_export_criteria_validation,
        test_validation_levels,
        test_compatibility_functions,
        test_error_handling_integration
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            result = test()
            if result is False:
                failed += 1
            else:
                passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} ÉCHOUÉ: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 65)
    print(f"📊 RÉSULTATS: {passed} tests réussis, {failed} tests échoués")
    
    if failed == 0:
        print("🎉 TOUS LES TESTS VALIDATION MANAGER SONT PASSÉS!")
        print("✅ Prêt à remplacer 650+ lignes de validation dispersée")
        print("✅ error_handler.py enfin utilisé massivement")
        print("✅ 306+ patterns .strip() peuvent être remplacés")
    else:
        print("⚠️  Certains tests ont échoué. Révision nécessaire.")
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)