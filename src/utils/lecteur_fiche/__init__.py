"""
Lecteur de fiches produit du site (CDC docs/cdc_import_fiches_site.md, étape 1)

Lecture seule, sans Qt ni base : une description ou une page publique de
fiche devient des données structurées, avec ce qui n'a pas été compris.
Le rapprochement avec la base, l'aperçu et l'écriture viennent ensuite.
"""

from src.utils.lecteur_fiche.lecteur import (
    LectureFiche, LigneAppareil, LigneEquivalentes, NonCompris, ScoreProfil,
    NATURES_NON_COMPRIS, decouper_references, lire_description,
)
from src.utils.lecteur_fiche.modeles import (
    ModeleLecture, Repere, modele_depuis_profil, modeles_depuis_config,
)
from src.utils.lecteur_fiche.normalisation import Bloc, normaliser
from src.utils.lecteur_fiche.page_publique import (
    LigneTableSite, PagePublique, ean13_valide, extraire_description,
    id_product_depuis_url, lire_page_publique,
)

__all__ = [
    'Bloc', 'normaliser',
    'ModeleLecture', 'Repere', 'modele_depuis_profil', 'modeles_depuis_config',
    'LectureFiche', 'LigneAppareil', 'LigneEquivalentes', 'NonCompris', 'ScoreProfil',
    'NATURES_NON_COMPRIS', 'decouper_references', 'lire_description',
    'LigneTableSite', 'PagePublique', 'ean13_valide', 'extraire_description',
    'id_product_depuis_url', 'lire_page_publique',
]
