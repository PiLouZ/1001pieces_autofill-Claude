"""
Normalisation de la casse des marques à l'import (v3.82.0)

Les fichiers fournisseurs écrivent souvent la marque tout en capitales
(« DELTA », « HEXATHERM ») alors qu'elle existe déjà en base sous la forme
« Delta ». Sans normalisation, chaque import crée une variante de plus — la base
en portait déjà une : « MIDEA » (11 appareils) à côté de « Midea » (3).

Deux règles, dans cet ordre :
1. La base fait foi : une marque connue, comparée sans casse, accents, espaces ni
   tirets, reprend l'orthographe de la base (« SCHOLTES » → « Scholtès »,
   « HOTPOINT ARISTON » → « Hotpoint-Ariston »). « AEG » reste « AEG ».
2. Marque nouvelle tout en capitales, de plus de 4 caractères : majuscule en tête
   de chaque mot et après un tiret (« ARTHUR-MARTIN » → « Arthur-Martin »). Les
   sigles courts (« CDA », « JPC ») et les casses mixtes (« KitchenAid ») ne sont
   jamais touchés.

Vérifié sur la base de production (488 marques) : la clé de comparaison ne fait
entrer en collision aucune paire de vraies marques distinctes, seulement
MIDEA/Midea.
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from .base_service import BaseService

# Au-delà de cette longueur, une marque tout en capitales est un nom écrit en
# capitales, pas un sigle
LONGUEUR_MAX_SIGLE = 4

_SEPARATEURS = re.compile(r"[\s\-_.&+']")


def cle_marque(marque: str) -> str:
    """Clé de comparaison : sans casse, accents, espaces ni ponctuation de liaison."""
    decomposee = unicodedata.normalize('NFKD', marque or '')
    sans_accents = ''.join(c for c in decomposee if not unicodedata.combining(c))
    return _SEPARATEURS.sub('', sans_accents.lower())


def est_en_capitales(marque: str) -> bool:
    """Vrai si la marque contient des lettres et qu'elles sont toutes majuscules."""
    return marque == marque.upper() and any(c.isalpha() for c in marque)


def mettre_en_forme(marque: str) -> str:
    """Règle 2 : « ARTHUR-MARTIN » → « Arthur-Martin ». Sigle court ou casse
    mixte : inchangé."""
    if len(marque) <= LONGUEUR_MAX_SIGLE or not est_en_capitales(marque):
        return marque
    # Chaque segment entre séparateurs (espace, tiret, apostrophe) prend une
    # majuscule initiale ; les séparateurs eux-mêmes sont conservés
    morceaux = re.split(r"([\s\-'])", marque)
    return ''.join(m[:1].upper() + m[1:].lower() if m and not _SEPARATEURS.fullmatch(m) else m
                   for m in morceaux)


class MarqueNormalisationService(BaseService):
    """Aligne les marques importées sur l'orthographe déjà présente en base."""

    def __init__(self, db_manager, parent_window=None):
        super().__init__(parent_window)
        self.db_manager = db_manager
        self._canoniques: Optional[Dict[str, str]] = None
        # (marque brute, marque retenue) → nombre de lignes, pour la trace d'import
        self._alignements: Dict[Tuple[str, str], int] = {}

    def charger(self) -> None:
        """Lire les marques de la base (une requête par import, ~500 valeurs).

        Plusieurs orthographes pour une même clé : la plus fréquente l'emporte.
        """
        lignes = self.db_manager.execute_query(
            "SELECT manufacturer, COUNT(*) FROM appareils "
            "WHERE manufacturer IS NOT NULL AND TRIM(manufacturer) <> '' "
            "GROUP BY manufacturer ORDER BY COUNT(*) DESC"
        )
        if not isinstance(lignes, (list, tuple)):
            # Base indisponible : seule la règle 2 s'applique, l'import continue
            lignes = []
        canoniques: Dict[str, str] = {}
        for marque, _nb in lignes:
            canoniques.setdefault(cle_marque(marque), marque)
        self._canoniques = canoniques
        self._alignements = {}

    def normaliser(self, marque: str) -> str:
        """Marque à enregistrer pour la valeur importée `marque`."""
        marque = (marque or '').strip()
        if not marque:
            return marque
        if self._canoniques is None:
            self.charger()

        cle = cle_marque(marque)
        retenue = self._canoniques.get(cle)
        if retenue is None:
            retenue = mettre_en_forme(marque)
            # Une marque nouvelle devient la référence pour la suite de l'import :
            # « NEWCO » puis « Newco » dans le même lot donnent une seule marque
            self._canoniques[cle] = retenue

        if retenue != marque:
            self._alignements[(marque, retenue)] = self._alignements.get((marque, retenue), 0) + 1
        return retenue

    def alignements(self) -> List[Tuple[str, str, int]]:
        """Corrections faites depuis le dernier chargement, triées par marque brute."""
        return sorted((brute, retenue, nb) for (brute, retenue), nb in self._alignements.items())

    @staticmethod
    def lignes(alignements: List[Tuple[str, str, int]]) -> List[str]:
        """['DELTA → Delta (7),', 'HEXATHERM → Hexatherm (1)'] : une par marque,
        virgule sauf sur la dernière."""
        textes = [f"{brute} → {retenue} ({nb})" for brute, retenue, nb in alignements]
        return [t + ',' for t in textes[:-1]] + textes[-1:]

    @classmethod
    def resume(cls, alignements: List[Tuple[str, str, int]]) -> str:
        """« DELTA → Delta (7), HEXATHERM → Hexatherm (1) » (journal)."""
        return ' '.join(cls.lignes(alignements))
