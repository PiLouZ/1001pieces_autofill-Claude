"""
❌ DEPRECATED - FICHIER DÉPRÉCIÉ ❌

Ce fichier a été remplacé par unified_export_service.py dans le cadre de la refactorisation Phase 1.

REMPLACEMENT :
- ExportService → UnifiedExportService
- Toutes les fonctionnalités ont été intégrées dans le service unifié

STATUT : À supprimer après validation complète de la migration

Date de dépréciation : Phase 1 Refactoring
Remplacé par : src/services/unified_export_service.py
"""

import warnings

warnings.warn(
    "export_service.py est déprécié. Utilisez unified_export_service.py à la place.",
    DeprecationWarning,
    stacklevel=2
)