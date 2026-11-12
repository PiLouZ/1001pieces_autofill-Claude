"""
Rapprochement des fiches du site avec la base (CDC docs/cdc_import_fiches_site.md, étape 2)

Lecture seule, sans Qt : une LectureFiche (étape 1) devient, pour chaque
élément (pièce, appareils, remplacements, équivalences), un niveau et une
raison, avec les doutes regroupés par catégorie. L'aperçu et l'écriture
viennent ensuite (étape 3).
"""

from src.utils.rapprochement_fiche.acces_base import (
    AccesBaseLecture, AppareilBase, IndexMarque, StatutPiece, forme_normalisee,
)
from src.utils.rapprochement_fiche.configuration import (
    CONFIGURATION_PAR_DEFAUT, ConfigurationRapprochement, Origine, charger_configuration,
)
from src.utils.rapprochement_fiche.rapprochement import rapprocher
from src.utils.rapprochement_fiche.resultat import (
    CATEGORIES_DOUTES, LIENS, NIVEAUX, STATUTS_EQUIVALENCE, STATUTS_REMPLACEMENT,
    AppareilRapproche, Doute, Equivalence, Identite, Rapprochement, Remplacement,
)

__all__ = [
    'AccesBaseLecture', 'AppareilBase', 'IndexMarque', 'StatutPiece', 'forme_normalisee',
    'CONFIGURATION_PAR_DEFAUT', 'ConfigurationRapprochement', 'Origine', 'charger_configuration',
    'rapprocher',
    'CATEGORIES_DOUTES', 'LIENS', 'NIVEAUX', 'STATUTS_EQUIVALENCE', 'STATUTS_REMPLACEMENT',
    'AppareilRapproche', 'Doute', 'Equivalence', 'Identite', 'Rapprochement', 'Remplacement',
]
