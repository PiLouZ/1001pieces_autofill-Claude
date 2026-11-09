"""
Générateur de titres de fiches produits (v3.99.0)

Titre construit à partir du libellé de la pièce, des types d'appareils, des
marques et de la référence la plus récente, selon un gabarit configurable
(profils de l'onglet « Titre » de la configuration des exports), par exemple :
    « {libelle} pour {type} {marques} - {reference} »
    → « Pompe de vidange pour lave-linge Bosch, Siemens et Neff - 00145787 »

Contrairement au méta title, aucune limite de largeur Google : le libellé et la
référence ne sont jamais raccourcis. Seules les marques (puis les types en plus
du premier) sont retirées, en partant de la fin, pour tenir dans la longueur
maximale du profil. Sans module Qt : testable seul.
"""

from typing import Any, Dict, List

from .seo_generator import SEOGenerator


# Variables disponibles dans le gabarit d'un profil Titre
VARIABLES_TITRE = ["{libelle}", "{type}", "{marques}", "{reference}"]


class TitreProduitGenerator:
    """Rendu d'un titre de fiche produit selon un profil (dict de réglages)."""

    # Un type d'appareil est cité avec le premier s'il couvre au moins 80 % de
    # ses modèles (décision client 2026-10-23 : « s'ils pèsent autant, ou à peu
    # de chose près »).
    SEUIL_TYPES_PROCHES = 0.8

    def __init__(self):
        # Normalisation du libellé, des types et des marques : la même que les métas
        self._seo = SEOGenerator()

    @classmethod
    def types_proches(cls, poids_types: Dict[str, int], max_types: int) -> List[str]:
        """
        Types du plus au moins couvrant (à égalité, ordre alphabétique) : le premier,
        suivi de ceux qui pèsent au moins SEUIL_TYPES_PROCHES fois autant, `max_types`
        au plus.
        """
        if not poids_types:
            return []
        classes = sorted(poids_types.items(), key=lambda x: (-x[1], x[0].casefold(), x[0]))
        plancher = classes[0][1] * cls.SEUIL_TYPES_PROCHES
        retenus = [t for t, poids in classes if poids >= plancher]
        return retenus[:max(1, int(max_types))]

    @staticmethod
    def joindre(elements: List[str], separateur: str, dernier_separateur: str) -> str:
        """« A », « A et B », « A, B et C »."""
        if len(elements) <= 1:
            return "".join(elements)
        return separateur.join(elements[:-1]) + dernier_separateur + elements[-1]

    def _types_normalises(self, types: List[str]) -> List[str]:
        vus, resultat = set(), []
        for t in types:
            t = self._seo._normalize_type(t) if isinstance(t, str) else ""
            if t and t not in vus:
                vus.add(t)
                resultat.append(t)
        return resultat

    def _rendre(self, profil: Dict[str, Any], libelle: str, types: List[str],
                marques: List[str], reference: str) -> str:
        valeurs = {
            '{libelle}': libelle,
            '{type}': self.joindre(types, profil.get('separateur_types', ", "),
                                   profil.get('dernier_separateur_types', " et ")),
            '{marques}': self.joindre(marques, profil.get('separateur_marques', ", "),
                                      profil.get('dernier_separateur_marques', " et ")),
            '{reference}': reference,
        }
        titre = profil.get('template', "")
        for variable, valeur in valeurs.items():
            titre = titre.replace(variable, valeur)
        # Un champ vide ne laisse ni double espace ni espace en bord
        return " ".join(titre.split())

    def generer(self, profil: Dict[str, Any], libelle: str, types: List[str],
                marques: List[str], reference: str, appellations=None) -> Dict[str, Any]:
        """
        Titre selon `profil`, avec `types` et `marques` classés du plus au moins
        couvrant. Au-delà de `max_caracteres` (0 = sans limite), on retire la
        dernière marque jusqu'à n'en garder qu'une, puis le dernier type jusqu'à
        n'en garder qu'un ; jamais le libellé ni la référence. Coupe sans mention.

        `appellations` (Appellations, facultatif) : chaque type peut être cité sous
        une autre appellation si le champ « titre » varie, à condition de ne faire
        retirer ni marque ni type de plus qu'avec les types en base.
        """
        libelle_net = self._seo._adjust_first_char((libelle or "").strip(), upper=True)
        reference_nette = (reference or "").strip()
        types_retenus = self._types_normalises(types)[:max(1, int(profil.get('max_types', 3)))]
        marques_dispo = [m for m in SEOGenerator._marques_uniques(marques) if m != "multi-marques"]
        marques_retenues = marques_dispo[:max(1, int(profil.get('max_marques', 4)))]
        limite = int(profil.get('max_caracteres', 0) or 0)

        def _ajuster(types_cites, marques_citees):
            complet = self._rendre(profil, libelle_net, types_cites, marques_citees,
                                   reference_nette)
            rendu = complet
            while limite and len(rendu) > limite:
                if len(marques_citees) > 1:
                    marques_citees = marques_citees[:-1]
                elif len(types_cites) > 1:
                    types_cites = types_cites[:-1]
                else:
                    break
                rendu = self._rendre(profil, libelle_net, types_cites, marques_citees,
                                     reference_nette)
            return complet, rendu, types_cites, marques_citees

        titre_complet, titre, types_cites, marques_finales = _ajuster(types_retenus,
                                                                       marques_retenues)
        appellations_citees = list(types_cites)
        if appellations is not None:
            termes = []
            for t in types_retenus:
                terme = appellations.choisir(t, reference_nette, 'titre').terme
                if terme not in termes:
                    termes.append(terme)
            if termes != types_retenus:
                complet_v, titre_v, types_v, marques_v = _ajuster(termes, marques_retenues)
                if len(types_v) >= len(types_cites) and len(marques_v) >= len(marques_finales):
                    titre_complet, titre, appellations_citees, marques_finales = (
                        complet_v, titre_v, types_v, marques_v)
                    types_cites = types_retenus[:len(types_v)]
        marques_retenues, types_retenus = marques_finales, types_cites

        return {
            'titre': titre,
            'longueur': len(titre),
            'info': {
                'raccourci': len(titre) < len(titre_complet),
                'dans_la_limite': not limite or len(titre) <= limite,
                'marques_retenues': marques_retenues,
                'nb_marques_disponibles': len(marques_dispo),
                'types_retenus': types_retenus,
                'appellations': appellations_citees,
            },
        }
