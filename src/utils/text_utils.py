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


def cle_tri_naturel(texte):
    """
    Clé de tri alphanumérique « naturel » : insensible à la casse et aux
    accents, les nombres comparés par leur valeur.

    Ex: sorted(['Profil 10', 'profil 2', 'Équipe'], key=cle_tri_naturel)
        -> ['Équipe', 'profil 2', 'Profil 10'].

    Args:
        texte: Le texte à trier (str ou None).

    Returns:
        tuple: Morceaux alternés (0, nombre) / (1, texte) comparables entre eux.
    """
    morceaux = re.split(r'(\d+)', strip_accents(texte).casefold())
    return tuple((0, int(m)) if m.isdigit() else (1, m) for m in morceaux if m)


def decouper_refs(texte):
    """
    Découpe une saisie de références de pièces en liste, sans doublon ni vide.

    Le séparateur est l'espace (et tout blanc : tabulation, retour à la ligne
    d'un collage multi-lignes). L'ordre de saisie est conservé.

    Ex: '00420214  00427589 00420214' -> ['00420214', '00427589'].

    Args:
        texte: str, liste de str, ou None. Une liste est aplatie (chaque
            élément peut lui-même contenir plusieurs réfs séparées par des espaces).

    Returns:
        list[str]
    """
    if not texte:
        return []
    morceaux = texte if isinstance(texte, (list, tuple)) else [texte]
    refs = []
    for morceau in morceaux:
        for ref in str(morceau or '').split():
            if ref not in refs:
                refs.append(ref)
    return refs


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
