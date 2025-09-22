"""
Validateur de données pour l'application de gestion d'appareils
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.config import Config

@dataclass
class ValidationResult:
    """Résultat d'une validation"""
    is_valid: bool
    error_message: Optional[str] = None
    warning_message: Optional[str] = None
    suggestions: Optional[List[str]] = None

class DataValidator:
    """Classe de validation des données"""
    
    def __init__(self):
        self.validation_rules = self._initialize_validation_rules()
    
    def _initialize_validation_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialiser les règles de validation"""
        return {
            'type': {
                'max_length': Config.MAX_FIELD_LENGTH,
                'required': False,
                'regex': None,
                'custom_validator': None
            },
            'manufacturer': {
                'max_length': Config.MAX_FIELD_LENGTH,
                'required': False,
                'regex': None,
                'custom_validator': None
            },
            'ref_modele': {
                'max_length': 100,
                'required': False,
                'regex': None,  # Pas de regex restrictif - géré par custom_validator
                'custom_validator': self._validate_reference_format
            },
            'commercial_ref': {
                'max_length': 100,
                'required': False,
                'regex': None,  # Pas de regex restrictif - géré par custom_validator
                'custom_validator': self._validate_reference_format
            },
            'other_ref': {
                'max_length': 100,
                'required': False,
                'regex': None,  # Pas de regex restrictif - géré par custom_validator
                'custom_validator': self._validate_reference_format
            },
            'category': {
                'max_length': 50,
                'required': False,
                'regex': None,
                'custom_validator': None
            },
            'notes': {
                'max_length': 1000,
                'required': False,
                'regex': None,
                'custom_validator': None
            }
        }
    
    def validate_field(self, field_name: str, value: str, 
                      context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Valider un champ spécifique"""
        if field_name not in self.validation_rules:
            return ValidationResult(
                is_valid=False, 
                error_message=f"Champ inconnu: {field_name}"
            )
        
        rules = self.validation_rules[field_name]
        
        # Validation de la longueur
        if value and len(value) > rules['max_length']:
            return ValidationResult(
                is_valid=False,
                error_message=Config.get_validation_error(
                    f"{field_name}_too_long",
                    max_length=rules['max_length']
                )
            )
        
        # Validation du format avec regex
        if value and rules['regex']:
            if not re.match(rules['regex'], value):
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Format invalide pour {field_name}: {value}"
                )
        
        # Validation personnalisée
        if rules['custom_validator']:
            result = rules['custom_validator'](value, context)
            if not result.is_valid:
                return result
        
        return ValidationResult(is_valid=True)
    
    def validate_record(self, record: Dict[str, str], 
                       context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Valider un enregistrement complet"""
        errors = []
        warnings = []
        suggestions = []
        
        # Valider chaque champ
        for field_name, value in record.items():
            if field_name in self.validation_rules:
                result = self.validate_field(field_name, value, context)
                if not result.is_valid:
                    errors.append(result.error_message)
                if result.warning_message:
                    warnings.append(result.warning_message)
                if result.suggestions:
                    suggestions.extend(result.suggestions)
        
        # Validations inter-champs
        cross_field_result = self._validate_cross_fields(record, context)
        if not cross_field_result.is_valid:
            errors.append(cross_field_result.error_message)
        if cross_field_result.warning_message:
            warnings.append(cross_field_result.warning_message)
        if cross_field_result.suggestions:
            suggestions.extend(cross_field_result.suggestions)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            error_message='; '.join(errors) if errors else None,
            warning_message='; '.join(warnings) if warnings else None,
            suggestions=suggestions if suggestions else None
        )
    
    def _validate_reference_format(self, value: str, 
                                  context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Validation personnalisée pour les références - TRÈS PERMISSIVE"""
        if not value:
            return ValidationResult(is_valid=True)
        
        # Nettoyer la valeur en supprimant les espaces au début/fin
        cleaned_value = value.strip()
        if not cleaned_value:
            return ValidationResult(is_valid=True)
        
        # Vérifier seulement les caractères vraiment problématiques pour les bases de données/fichiers
        # Autoriser: espaces, parenthèses, barres obliques, plus, deux-points, tirets, points, etc.
        forbidden_chars = ['\0', '\r', '\n', '\t']  # Seulement les caractères de contrôle dangereux
        for char in forbidden_chars:
            if char in cleaned_value:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Caractère de contrôle interdit dans la référence"
                )
        
        # Vérifier que ce n'est pas que des espaces ou caractères vides
        if not cleaned_value.strip():
            return ValidationResult(
                is_valid=False,
                error_message="La référence ne peut pas être vide ou contenir seulement des espaces"
            )
        
        # Suggestions d'amélioration (mais n'empêchent pas la validation)
        suggestions = []
        if len(cleaned_value) != len(cleaned_value.strip()):
            suggestions.append("Supprimer les espaces au début/fin de la référence")
        
        if len(cleaned_value) > 50:
            suggestions.append("La référence est très longue, considérer la raccourcir")
        
        return ValidationResult(
            is_valid=True,
            suggestions=suggestions if suggestions else None
        )
    
    def _validate_cross_fields(self, record: Dict[str, str], 
                              context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Validations entre plusieurs champs"""
        warnings = []
        suggestions = []
        
        # Vérifier qu'au moins un champ critique est rempli
        critical_fields = ['type', 'manufacturer', 'ref_modele', 'commercial_ref']
        filled_critical = sum(1 for field in critical_fields if record.get(field, '').strip())
        
        if filled_critical == 0:
            return ValidationResult(
                is_valid=False,
                error_message="Au moins un champ parmi Type, Fabricant, ou Référence doit être rempli"
            )
        
        # Suggestions d'amélioration
        if not record.get('type', '').strip():
            suggestions.append("Renseigner le type d'appareil")
        
        if not record.get('manufacturer', '').strip():
            suggestions.append("Renseigner le fabricant")
        
        # Vérifier la cohérence des références
        refs = [record.get('ref_modele', ''), record.get('commercial_ref', ''), record.get('other_ref', '')]
        unique_refs = set(ref.strip() for ref in refs if ref.strip())
        
        if len(unique_refs) < len([ref for ref in refs if ref.strip()]):
            warnings.append("Certaines références sont identiques")
        
        return ValidationResult(
            is_valid=True,
            warning_message='; '.join(warnings) if warnings else None,
            suggestions=suggestions if suggestions else None
        )
    
    def validate_import_data(self, data: List[List[str]]) -> Dict[str, Any]:
        """Valider des données d'import"""
        validation_summary = {
            'total_rows': len(data),
            'valid_rows': 0,
            'invalid_rows': 0,
            'warnings': 0,
            'errors': [],
            'row_details': []
        }
        
        for row_idx, row_data in enumerate(data):
            # Convertir la ligne en dictionnaire
            record = {}
            for col_idx, value in enumerate(row_data):
                if col_idx < len(Config.DB_HEADERS):
                    record[Config.DB_HEADERS[col_idx]] = value
            
            # Valider la ligne
            result = self.validate_record(record)
            
            row_detail = {
                'row_index': row_idx,
                'is_valid': result.is_valid,
                'errors': result.error_message,
                'warnings': result.warning_message,
                'suggestions': result.suggestions
            }
            
            validation_summary['row_details'].append(row_detail)
            
            if result.is_valid:
                validation_summary['valid_rows'] += 1
            else:
                validation_summary['invalid_rows'] += 1
                validation_summary['errors'].append(f"Ligne {row_idx + 1}: {result.error_message}")
            
            if result.warning_message:
                validation_summary['warnings'] += 1
        
        return validation_summary
    
    def validate_duplicate_references(self, references: List[str], 
                                    db_manager = None) -> ValidationResult:
        """Valider les références pour éviter les doublons"""
        if not db_manager:
            return ValidationResult(is_valid=True)
        
        duplicates = []
        for ref in references:
            if ref.strip() and db_manager.check_duplicate_reference(ref.strip()):
                duplicates.append(ref.strip())
        
        if duplicates:
            return ValidationResult(
                is_valid=False,
                error_message=f"Références existantes: {', '.join(duplicates)}"
            )
        
        return ValidationResult(is_valid=True)
    
    def suggest_data_completion(self, record: Dict[str, str], 
                               similar_records: List[Dict[str, str]]) -> List[str]:
        """Suggérer des complétions de données basées sur des enregistrements similaires"""
        suggestions = []
        
        # Analyser les enregistrements similaires
        for similar in similar_records:
            # Suggérer le type si manquant
            if not record.get('type', '').strip() and similar.get('type', '').strip():
                suggestions.append(f"Type suggéré: {similar['type']}")
            
            # Suggérer le fabricant si manquant
            if not record.get('manufacturer', '').strip() and similar.get('manufacturer', '').strip():
                suggestions.append(f"Fabricant suggéré: {similar['manufacturer']}")
            
            # Suggérer la catégorie si manquante
            if not record.get('category', '').strip() and similar.get('category', '').strip():
                suggestions.append(f"Catégorie suggérée: {similar['category']}")
        
        return list(set(suggestions))  # Supprimer les doublons
    
    def validate_piece_reference(self, ref_piece: str) -> ValidationResult:
        """Valider une référence de pièce"""
        if not ref_piece or not ref_piece.strip():
            return ValidationResult(
                is_valid=False,
                error_message="La référence de pièce ne peut pas être vide"
            )
        
        # Vérifier la longueur
        if len(ref_piece) > 100:
            return ValidationResult(
                is_valid=False,
                error_message="La référence de pièce ne peut pas dépasser 100 caractères"
            )
        
        # Vérifier seulement les caractères vraiment problématiques
        forbidden_chars = ['\0', '\r', '\n', '\t']
        for char in forbidden_chars:
            if char in ref_piece:
                return ValidationResult(
                    is_valid=False,
                    error_message="Caractère de contrôle interdit dans la référence de pièce"
                )
        
        return ValidationResult(is_valid=True)
    
    def get_validation_rules(self) -> Dict[str, Dict[str, Any]]:
        """Récupérer les règles de validation"""
        return self.validation_rules.copy()
    
    def add_custom_rule(self, field_name: str, rule_name: str, rule_value: Any):
        """Ajouter une règle de validation personnalisée"""
        if field_name not in self.validation_rules:
            self.validation_rules[field_name] = {}
        
        self.validation_rules[field_name][rule_name] = rule_value
    
    def validate_category(self, category: str, available_categories: List[str]) -> ValidationResult:
        """Valider une catégorie"""
        if not category:
            return ValidationResult(is_valid=True)
        
        if category not in available_categories:
            return ValidationResult(
                is_valid=True,  # Permettre les nouvelles catégories
                warning_message=f"Nouvelle catégorie: {category}",
                suggestions=[f"Catégories existantes: {', '.join(available_categories[:5])}"]
            )
        
        return ValidationResult(is_valid=True)