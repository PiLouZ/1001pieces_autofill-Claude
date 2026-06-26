"""
Utilitaires de traitement de texte
Centralise les fonctions de nettoyage et normalisation de texte
"""

import re
import unicodedata


def strip_accents(text):
    """
    Retire les accents/diacritiques d'un texte pour une comparaison insensible
    aux accents (recherche, filtrage d'auto-complétion).

    Décompose chaque caractère accentué en sa forme de base + marque combinante
    (Unicode NFKD), puis supprime les marques. Couvre toutes les voyelles
    accentuées et la cédille sans table de correspondance à maintenir.

    Ex: 'Jünker' -> 'Junker' ; 'Crémaillère' -> 'Cremaillere' ; 'çà' -> 'ca'.

    Args:
        text: Le texte à normaliser (str ou None).

    Returns:
        str: Le texte sans accents (chaîne vide si entrée vide/None).
    """
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(text))
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def clean_display_text(text):
    """
    Nettoie le texte pour l'affichage en supprimant les caractères illisibles.

    Opérations:
    - Conversion en string si nécessaire
    - Suppression des caractères de contrôle (sauf retour à la ligne et tabulation)
    - Normalisation UTF-8 avec remplacement des caractères invalides
    - Suppression des espaces multiples
    - Nettoyage des caractères invisibles ou problématiques

    Args:
        text: Le texte à nettoyer (str, int, float, None)

    Returns:
        str: Le texte nettoyé, ou "" si le texte est vide
    """
    if not text:
        return ""

    # Convertir en string si nécessaire
    text = str(text)

    # Supprimer les caractères de contrôle (sauf retour à la ligne et tabulation)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)

    # Remplacer les caractères non-UTF8 par un caractère de substitution
    # Note: Plus de try/except nécessaire - encode() avec errors='replace' gère automatiquement
    text = text.encode('utf-8', errors='replace').decode('utf-8')

    # Supprimer les espaces multiples
    text = re.sub(r'\s+', ' ', text)

    # Nettoyer les caractères invisibles ou problématiques
    text = text.strip()

    return text
