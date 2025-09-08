"""
❌ DEPRECATED - FICHIER DÉPRÉCIÉ ❌

Ce fichier a été remplacé par unified_dialog_service.py dans le cadre de la refactorisation Phase 2.

REMPLACEMENT :
- CategoryDialog → UnifiedDialogService.get_categories() (méthode statique)
- NotesDialog → UnifiedDialogService.get_notes() (méthode statique)
- DialogService → UnifiedDialogService (avec factory methods pour rétrocompatibilité)

STATUT : À supprimer après validation complète de la migration

Date de dépréciation : Phase 2 Refactoring
Remplacé par : src/services/unified_dialog_service.py
"""

import warnings

warnings.warn(
    "services/dialog_service.py est déprécié. Utilisez unified_dialog_service.py à la place.",
    DeprecationWarning,
    stacklevel=2
)