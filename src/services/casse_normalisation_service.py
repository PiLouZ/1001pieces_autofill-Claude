"""
Normalisation de la casse des marques et des types (v3.82.0, types et saisie
manuelle v3.83.0)

Les fichiers fournisseurs écrivent souvent la marque tout en capitales
(« DELTA », « HEXATHERM ») alors qu'elle existe déjà en base sous la forme
« Delta ». Sans normalisation, chaque import créait une variante de plus — la base
en portait déjà une : « MIDEA » (11 appareils) à côté de « Midea » (3). Le même
risque existe pour le type (« CHAUFFAGE » à côté de « Chauffage ») et pour la
saisie manuelle dans le tableau.

Deux règles, dans cet ordre :
1. La base fait foi : une valeur connue, comparée sans casse, accents, espaces ni
   tirets, reprend l'orthographe de la base (« SCHOLTES » → « Scholtès »,
   « HOTPOINT ARISTON » → « Hotpoint-Ariston »). « AEG » reste « AEG ».
2. Valeur nouvelle tout en capitales, de plus de 4 caractères :
   - marque : majuscule en tête de chaque mot et après un tiret
     (« ARTHUR-MARTIN » → « Arthur-Martin ») ;
   - type : majuscule initiale seule, comme les 42 types en base
     (« CHAUFFE-EAU » → « Chauffe-eau »).
   Les sigles courts (« CDA ») et les casses mixtes (« KitchenAid ») ne sont
   jamais touchés.

Marques seulement, avant ces deux règles : les écritures connues d'une même
marque (`AliasMarques.ALIAS`, « Glem » → « Glem Gas », « Concord » → « Concorde »,
ménage des marques 2026-11-24) sont ramenées à son nom.

Vérifié sur la base de production (488 marques, 42 types) : la clé de
comparaison ne fait entrer en collision aucune paire de vraies valeurs
distinctes, seulement MIDEA/Midea (fusionnés depuis).
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from ..core.constants import AliasMarques
from .base_service import BaseService

# Au-delà de cette longueur, une valeur tout en capitales est un nom écrit en
# capitales, pas un sigle
LONGUEUR_MAX_SIGLE = 4

# Colonnes normalisées (nom de colonne SQL fixe : jamais issu d'une saisie)
COLONNES = ('manufacturer', 'type')

_SEPARATEURS = re.compile(r"[\s\-_.&+']")


def cle_marque(valeur: str) -> str:
    """Clé de comparaison : sans casse, accents, espaces ni ponctuation de liaison."""
    decomposee = unicodedata.normalize('NFKD', valeur or '')
    sans_accents = ''.join(c for c in decomposee if not unicodedata.combining(c))
    return _SEPARATEURS.sub('', sans_accents.lower())


def est_en_capitales(valeur: str) -> bool:
    """Vrai si la valeur contient des lettres et qu'elles sont toutes majuscules."""
    return valeur == valeur.upper() and any(c.isalpha() for c in valeur)


def _a_normaliser(valeur: str) -> bool:
    return len(valeur) > LONGUEUR_MAX_SIGLE and est_en_capitales(valeur)


def mettre_en_forme(marque: str) -> str:
    """Règle 2 des marques : « ARTHUR-MARTIN » → « Arthur-Martin ». Sigle court
    ou casse mixte : inchangé."""
    if not _a_normaliser(marque):
        return marque
    # Chaque segment entre séparateurs (espace, tiret, apostrophe) prend une
    # majuscule initiale ; les séparateurs eux-mêmes sont conservés
    morceaux = re.split(r"([\s\-'])", marque)
    return ''.join(m[:1].upper() + m[1:].lower() if m and not _SEPARATEURS.fullmatch(m) else m
                   for m in morceaux)


def mettre_en_forme_type(type_appareil: str) -> str:
    """Règle 2 des types : « CHAUFFE-EAU » → « Chauffe-eau ». Sigle court ou
    casse mixte : inchangé."""
    if not _a_normaliser(type_appareil):
        return type_appareil
    return type_appareil[:1].upper() + type_appareil[1:].lower()


_MISE_EN_FORME = {'manufacturer': mettre_en_forme, 'type': mettre_en_forme_type}

# Clé d'une écriture → nom de la marque (colonne `manufacturer` seulement)
_ALIAS = {cle_marque(ecriture): nom for ecriture, nom in AliasMarques.ALIAS.items()}


class CasseNormalisationService(BaseService):
    """Aligne une valeur (marque ou type) sur l'orthographe déjà présente en base."""

    def __init__(self, db_manager, colonne: str = 'manufacturer', parent_window=None):
        if colonne not in COLONNES:
            raise ValueError(f"Colonne non normalisable : {colonne}")
        super().__init__(parent_window)
        self.db_manager = db_manager
        self.colonne = colonne
        self._mise_en_forme = _MISE_EN_FORME[colonne]
        self._canoniques: Optional[Dict[str, str]] = None
        # (valeur brute, valeur retenue) → nombre de lignes, pour la trace d'import
        self._alignements: Dict[Tuple[str, str], int] = {}

    def _lire(self, methode: str) -> list:
        """Lecture de la colonne par la méthode `methode` de la base."""
        lignes = getattr(self.db_manager, methode)(self.colonne)
        # Base indisponible : seule la règle 2 s'applique, l'appelant continue
        return lignes if isinstance(lignes, (list, tuple)) else []

    def charger(self) -> None:
        """Lire les valeurs de la base (une requête par import, ~90 ms).

        Plusieurs orthographes pour une même clé : la plus fréquente l'emporte.
        Remet aussi les traces d'alignement à zéro.
        """
        lignes = self._lire('valeurs_frequentes_colonne')
        canoniques: Dict[str, str] = {}
        for valeur, _nb in lignes:
            canoniques.setdefault(cle_marque(valeur), valeur)
        self._canoniques = canoniques
        self._alignements = {}

    def _completer_depuis_la_base(self) -> None:
        """Ajouter les valeurs apparues en base depuis le chargement (import,
        restauration…). Lecture des seules valeurs distinctes, servie par l'index
        (< 1 ms) : appelée à chaque valeur inconnue, elle évite qu'une liste
        chargée au lancement devienne périmée."""
        for ligne in self._lire('valeurs_colonne'):
            self._canoniques.setdefault(cle_marque(ligne[0]), ligne[0])

    def normaliser(self, valeur: str) -> str:
        """Valeur à enregistrer pour la valeur saisie ou importée `valeur`."""
        valeur = (valeur or '').strip()
        if not valeur:
            return valeur
        if self._canoniques is None:
            self.charger()

        cle = cle_marque(valeur)
        if self.colonne == 'manufacturer' and cle in _ALIAS:
            # « Glem » → « Glem Gas » ; puis l'orthographe de la base fait foi
            cle = cle_marque(_ALIAS[cle])
            self._canoniques.setdefault(cle, _ALIAS[cle_marque(valeur)])
        if cle not in self._canoniques:
            self._completer_depuis_la_base()
        retenue = self._canoniques.get(cle)
        if retenue is None:
            retenue = self._mise_en_forme(valeur)
            # Une valeur nouvelle devient la référence pour la suite :
            # « NEWCO » puis « Newco » dans le même lot donnent une seule marque
            self._canoniques[cle] = retenue

        if retenue != valeur:
            self._alignements[(valeur, retenue)] = self._alignements.get((valeur, retenue), 0) + 1
        return retenue

    def alignements(self) -> List[Tuple[str, str, int]]:
        """Corrections faites depuis le dernier chargement, triées par valeur brute."""
        return sorted((brute, retenue, nb) for (brute, retenue), nb in self._alignements.items())

    @staticmethod
    def lignes(alignements: List[Tuple[str, str, int]]) -> List[str]:
        """['DELTA → Delta (7),', 'HEXATHERM → Hexatherm (1)'] : une par valeur,
        virgule sauf sur la dernière."""
        textes = [f"{brute} → {retenue} ({nb})" for brute, retenue, nb in alignements]
        return [t + ',' for t in textes[:-1]] + textes[-1:]

    @classmethod
    def resume(cls, alignements: List[Tuple[str, str, int]]) -> str:
        """« DELTA → Delta (7), HEXATHERM → Hexatherm (1) » (journal)."""
        return ' '.join(cls.lignes(alignements))
