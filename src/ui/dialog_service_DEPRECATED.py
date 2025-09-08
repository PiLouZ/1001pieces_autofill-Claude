"""
❌ DEPRECATED - FICHIER DÉPRÉCIÉ ❌

Ce fichier a été remplacé par unified_dialog_service.py dans le cadre de la refactorisation Phase 2.

REMPLACEMENT :
- DialogService (ui/) → UnifiedDialogService.complex (méthodes d'instance)
- get_import_options_unified() → unified_dialog_service.get_import_options_unified()
- show_reference_selection_dialog() → unified_dialog_service.show_reference_selection_dialog()
- show_autocompletion_popup() → unified_dialog_service.show_autocompletion_popup()

STATUT : À supprimer après validation complète de la migration

Date de dépréciation : Phase 2 Refactoring
Remplacé par : src/services/unified_dialog_service.UnifiedDialogService
"""

import warnings

warnings.warn(
    "ui/dialog_service.py est déprécié. Utilisez unified_dialog_service.UnifiedDialogService à la place.",
    DeprecationWarning,
    stacklevel=2
)