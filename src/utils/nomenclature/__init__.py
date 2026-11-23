"""
Moteur des règles de nomenclature (CDC docs/cdc_regles_nomenclature.md § 6-7),
en fonctions pures, sans base ni Qt : testable seul, réutilisé par le service
(`RegleNomenclatureService`), puis par l'écran de revue (lot 4) et l'import (lot 5).

- `cles`       : clés normalisées d'un appareil (nom commercial, code usine) ;
- `moteur`     : règles compilées et résolution d'un appareil (§ 6.2) ;
- `force`      : force d'une proposition (§ 7) ;
- `decouverte` : découverte automatique de règles candidates (§ 6.3).
"""
