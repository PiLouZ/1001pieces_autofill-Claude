"""
❌ DEPRECATED - FICHIER DÉPRÉCIÉ ❌

Ce fichier a été remplacé par unified_export_service.MainExportService dans le cadre de la refactorisation Phase 1.

REMPLACEMENT :
- MainExportService (ui/) → MainExportService dans unified_export_service.py
- Toutes les fonctionnalités ont été intégrées dans le service unifié avec héritage propre

STATUT : À supprimer après validation complète de la migration

Date de dépréciation : Phase 1 Refactoring  
Remplacé par : src/services/unified_export_service.MainExportService
"""

import warnings

warnings.warn(
    "ui/export_service.py est déprécié. Utilisez unified_export_service.MainExportService à la place.",
    DeprecationWarning,
    stacklevel=2
)