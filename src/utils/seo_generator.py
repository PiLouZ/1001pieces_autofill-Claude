"""
Module de génération de métadonnées SEO
Inspiré du script.js pour e-commerce pièces détachées électroménager
"""

import random
from typing import List, Dict, Tuple, Optional
from .error_handler import handle_seo_generation_errors

class SEOGenerator:
    """Générateur de métadonnées SEO pour pièces détachées électroménager"""
    
    # Variantes pour les méta descriptions (inspiré du script.js)
    META_DESCRIPTION_TEMPLATES = [
        "Commandez {description} {reference} pour {type_appareil} {fabricants} chez un spécialiste des pièces détachées électroménager",
        "Obtenez {description} {reference} pour {type_appareil} {fabricants} auprès d'un expert des pièces détachées",
        "Achetez {description} {reference} pour {type_appareil} {fabricants} chez un fournisseur fiable de pièces détachées",
        "Découvrez {description} {reference} pour {type_appareil} {fabricants} et réparez vos appareils électroménagers facilement",
        "Trouvez {description} {reference} pour {type_appareil} {fabricants} chez le spécialiste de la réparation électroménager",
        "Commandez {description} {reference} pour {type_appareil} {fabricants} chez un expert de la réparation d'appareils",
        "Obtenez {description} {reference} pour {type_appareil} {fabricants} et réparez facilement vos appareils",
        "Achetez {description} {reference} pour {type_appareil} {fabricants} et redonnez vie à vos appareils électroménagers",
        "Retrouvez {description} {reference} pour {type_appareil} {fabricants} pour réparer vos appareils électroménagers",
        "Découvrez {description} {reference} pour {type_appareil} {fabricants} chez votre spécialiste pièces détachées",
        "Réparez votre {type_appareil} {fabricants} avec {description} {reference} — livraison rapide chez votre spécialiste",
        "En panne ? {description} {reference} pour {type_appareil} {fabricants} disponible chez votre réparateur agréé",
    ]

    # Templates avec comptage de modèles compatibles (utilisés quand n_modeles > 0)
    META_DESCRIPTION_COMPATIBLE_TEMPLATES = [
        "Commandez {description} {reference} — compatible avec {n_modeles} modèles {type_appareil} {fabricants}",
        "Trouvez {description} {reference} compatible avec {n_modeles} modèles {type_appareil} {fabricants}",
        "Achetez {description} {reference} — pièce compatible avec {n_modeles} appareils {fabricants}",
        "Réparez votre {type_appareil} {fabricants} : {description} {reference}, compatible {n_modeles} modèles",
    ]

    # Templates spécifiques aux pièces remplacées (ref_old → ref_current)
    # {ref_old} = ancienne référence recherchée, {reference} = référence courante
    META_DESCRIPTION_SUPERSEDED_TEMPLATES = [
        "Vous cherchez {ref_old} ? La référence actuelle est {reference} — commandez {description} pour {type_appareil} {fabricants}",
        "Référence {ref_old} remplacée par {reference} — {description} pour {type_appareil} {fabricants} chez votre spécialiste",
        "L'ancienne réf. {ref_old} est désormais {reference} — trouvez {description} pour {type_appareil} {fabricants}",
        "Nouvelle référence {reference} (remplace {ref_old}) — {description} pour {type_appareil} {fabricants}, livraison rapide",
    ]
    
    # Mots de liaison à supprimer en priorité pour préserver les marques
    FILLER_WORDS = [
        "pour", "de", "des", "du", "la", "le", "les", "d'", "l'",
        "avec", "sans", "sur", "sous", "dans", "par", "et"
    ]
    
    # Normalisation des types d'appareils (variantes orthographiques → forme canonique)
    TYPE_NORMALIZATION = {
        "lave linge": "lave-linge",
        "lave vaisselle": "lave-vaisselle",
        "seche linge": "sèche-linge",
        "sèche linge": "sèche-linge",
        "seche-linge": "sèche-linge",
        "micro ondes": "micro-ondes",
        "four micro ondes": "four micro-ondes",
        "four micro-ondes": "four micro-ondes",
        "refrigerateur": "réfrigérateur",
        "congelateur": "congélateur",
        "lave-vaisselle posable": "lave-vaisselle",
        "lave-linge frontal": "lave-linge",
        "lave-linge hublot": "lave-linge",
        "lave-linge top": "lave-linge top",
    }

    # Remplacements pour raccourcir (ordre de priorité par gain de caractères)
    WORD_REPLACEMENTS = {
        "réfrigérateur": "frigo",        # -7 caractères
        "lave-vaisselle": "LV",          # -11 caractères  
        "lave-linge": "LL",              # -7 caractères
        "sèche-linge": "SL",             # -8 caractères
        "micro-ondes": "micro-onde",     # -1 caractère
        "électroménager": "électromén.", # -3 caractères
        "électroménagers": "électromén.", # -4 caractères
        "cuisinière": "cuisin.",         # -4 caractères
        "congélateur": "congélo",        # -4 caractères
        "aspirateur": "aspiro",          # -4 caractères
    }
    
    def __init__(self):
        self.last_generation_info = {}

    def _normalize_type(self, type_appareil: str) -> str:
        """
        Normalise le type d'appareil : forme canonique + première lettre minuscule.
        Corrige les variantes orthographiques (espaces/tirets, accents manquants).
        """
        t = type_appareil.strip().lower()
        for variant, canonical in self.TYPE_NORMALIZATION.items():
            if t == variant:
                return canonical
        return t

    def _adjust_first_char(self, s: str, upper: bool) -> str:
        """
        Ajuste uniquement le premier caractère du libellé.
        - upper=True  → première lettre en majuscule (méta title)
        - upper=False → première lettre en minuscule (méta description)
        Si toute la chaîne est en majuscules (ex: "MOTEUR DE POMPE"),
        normalise d'abord en minuscules avant d'ajuster.
        Les majuscules internes (sigles, marques) sont préservées.
        """
        if not s:
            return s
        if s == s.upper() and any(c.isalpha() for c in s):
            s = s.lower()
        return (s[0].upper() + s[1:]) if upper else (s[0].lower() + s[1:])
    
    @handle_seo_generation_errors()
    def generate_meta_title(self, reference: str, description: str, type_appareil: str,
                           fabricants: List[str], max_length: int = 60,
                           ref_obsolete: Optional[str] = None) -> Dict[str, any]:
        """
        Générer un méta title optimisé avec priorité à l'inclusion d'au moins 1 marque.
        Format normal   : [ref] - [description] pour [type] [marques]
        Format obsolète : [ref_old]→[ref_current] [description] [type] [marques]
                          (fallback sur format normal si trop long)
        """
        reference_clean = reference.strip()
        description_clean = self._adjust_first_char(description.strip(), upper=True)
        type_clean = self._normalize_type(type_appareil)

        # ── Format supersession : [ref_old]→[ref_current] … ──────────────────
        if ref_obsolete:
            ref_old_clean = ref_obsolete.strip()
            prefix = f"{ref_old_clean}→{reference_clean}"
            remaining = max_length - len(prefix) - 1
            if remaining >= 10:
                fabricants_optimaux = self._maximize_brands_in_title(
                    fabricants, prefix, description_clean, type_clean,
                    max_length - len(prefix) - 1
                )
                base_title = f"{prefix} {description_clean} {type_clean} {fabricants_optimaux}".strip()
                if len(base_title) > max_length:
                    base_title = self._optimize_title_with_brands(base_title, fabricants_optimaux, max_length)
            else:
                ref_obsolete = None  # Préfixe trop long → format normal

        # ── Format normal (sans tiret séparateur) ─────────────────────────────
        if not ref_obsolete:
            fabricants_optimaux = self._maximize_brands_in_title(
                fabricants, reference_clean, description_clean, type_clean, max_length
            )
            base_title = f"{reference_clean} {description_clean} pour {type_clean} {fabricants_optimaux}"
            if len(base_title) > max_length:
                base_title = self._optimize_title_with_brands(base_title, fabricants_optimaux, max_length)

        # Informations de génération
        original_title = f"{reference_clean} - {description_clean} pour {type_clean} {fabricants_optimaux}"
        generation_info = {
            'original_length': len(original_title),
            'final_length': len(base_title),
            'truncated': len(base_title) < len(original_title),
            'within_limit': len(base_title) <= max_length,
            'fabricants_used': fabricants_optimaux,
            'fabricants_count': len(fabricants_optimaux.split()) if fabricants_optimaux else 0,
            'total_fabricants_available': len(fabricants),
            'brand_guaranteed': bool(fabricants_optimaux.strip()),
            'superseded': bool(ref_obsolete),
        }

        self.last_generation_info['title'] = generation_info

        return {
            'title': base_title,
            'length': len(base_title),
            'info': generation_info
        }
    
    @handle_seo_generation_errors()
    def generate_meta_description(self, reference: str, description: str, type_appareil: str,
                                 fabricants: List[str], max_length: int = 150,
                                 ref_obsolete: Optional[str] = None,
                                 n_modeles: int = 0) -> Dict[str, any]:
        """
        Générer une méta description aléatoire.
        - ref_obsolete : utilise les templates supersession (ancienne + nouvelle ref)
        - n_modeles > 0 : utilise les templates de compatibilité (X modèles compatibles)
        """
        reference_clean = reference.strip()
        description_clean = self._adjust_first_char(description.strip(), upper=False)
        type_clean = self._normalize_type(type_appareil)

        article = self._get_article(description_clean)
        description_with_article = f"{article} {description_clean}"

        # ── Choisir le pool de templates selon le contexte ───────────────────
        if ref_obsolete:
            template = random.choice(self.META_DESCRIPTION_SUPERSEDED_TEMPLATES)
        elif n_modeles > 0:
            template = random.choice(self.META_DESCRIPTION_COMPATIBLE_TEMPLATES)
        else:
            template = random.choice(self.META_DESCRIPTION_TEMPLATES)

        fabricants_str = self._select_fabricants_for_description(
            fabricants, template, reference_clean, description_clean, type_clean, max_length
        )

        # ── Instancier le template ────────────────────────────────────────────
        fmt_kwargs = dict(
            description=description_with_article,
            reference=reference_clean,
            type_appareil=type_clean,
            fabricants=fabricants_str,
        )
        if ref_obsolete:
            fmt_kwargs['ref_old'] = ref_obsolete.strip()
        if n_modeles > 0:
            fmt_kwargs['n_modeles'] = n_modeles

        description_text = template.format(**fmt_kwargs)

        final_description = self._smart_truncate_description(description_text, max_length)

        generation_info = {
            'template_used': template,
            'original_length': len(description_text),
            'final_length': len(final_description),
            'truncated': len(final_description) < len(description_text),
            'within_limit': len(final_description) <= max_length,
            'fabricants_used': fabricants_str,
            'fabricants_count': len(fabricants),
            'superseded': bool(ref_obsolete),
            'n_modeles': n_modeles,
        }

        self.last_generation_info['description'] = generation_info

        return {
            'description': final_description,
            'length': len(final_description),
            'info': generation_info
        }
    
    def _maximize_brands_in_title(self, fabricants: List[str], reference: str, 
                                description: str, type_appareil: str, max_length: int) -> str:
        """Maximiser le nombre de marques dans le titre pour atteindre ~60 caractères"""
        if not fabricants:
            return ""
        
        # Dédupliquer en préservant l'ordre de fréquence (trié par seo_service, plus présents d'abord)
        seen: set = set()
        unique_fabricants = []
        for f in fabricants:
            f = f.strip()
            if f and f not in seen:
                seen.add(f)
                unique_fabricants.append(f)
        
        # Calculer l'espace disponible pour les marques (format sans tiret séparateur)
        base_without_brands = f"{reference} {description} pour {type_appareil} "
        available_space = max_length - len(base_without_brands)
        
        # Construire la liste des marques optimale
        selected_brands = []
        current_length = 0
        
        for brand in unique_fabricants:
            # Calculer la longueur si on ajoute cette marque
            if selected_brands:
                # Ajouter un espace entre les marques
                new_length = current_length + 1 + len(brand)
            else:
                # Première marque
                new_length = len(brand)
            
            # Si ça rentre, ajouter la marque
            if new_length <= available_space:
                selected_brands.append(brand)
                current_length = new_length
            else:
                # Si on a déjà au moins une marque, on s'arrête
                if selected_brands:
                    break
                # Si même la première marque ne rentre pas, la prendre quand même
                else:
                    selected_brands.append(brand)
                    break
        
        # Si aucune marque sélectionnée, prendre au moins la première
        if not selected_brands and unique_fabricants:
            selected_brands = [unique_fabricants[0]]
        
        return " ".join(selected_brands)
    
    def _optimize_title_with_brands(self, title: str, required_brands: str, max_length: int) -> str:
        """
        Optimiser un titre en gardant obligatoirement les marques spécifiées
        1. Appliquer les raccourcis (réfrigérateur → frigo)
        2. Supprimer les mots de liaison (de, des, pour)
        3. Réduire le nombre de marques si nécessaire
        4. Tronquer intelligemment en dernier recours
        """
        if len(title) <= max_length:
            return title
        
        # Étape 1: Appliquer les raccourcis de mots
        optimized_title = self._apply_word_replacements(title)
        
        if len(optimized_title) <= max_length:
            return optimized_title
        
        # Étape 2: Supprimer les mots de liaison en préservant les marques
        optimized_title = self._remove_filler_words_keep_brands(optimized_title, required_brands)
        
        if len(optimized_title) <= max_length:
            return optimized_title
        
        # Étape 3: Si toujours trop long, réduire le nombre de marques
        optimized_title = self._reduce_brands_if_needed(optimized_title, max_length)

        # Étape 4: Troncature intelligente en dernier recours
        return self._smart_truncate_with_brands(optimized_title, required_brands, max_length)
    
    def _apply_word_replacements(self, title: str) -> str:
        """Appliquer les raccourcis de mots pour économiser des caractères"""
        result = title
        for original, replacement in self.WORD_REPLACEMENTS.items():
            result = result.replace(original, replacement)
            result = result.replace(original.capitalize(), replacement)
        return result
    
    def _remove_filler_words_keep_brands(self, title: str, required_brands: str) -> str:
        """Supprimer les mots de liaison tout en préservant les marques"""
        words = title.split()
        brand_words = required_brands.split() if required_brands else []
        
        result_words = []
        for word in words:
            word_lower = word.lower().rstrip("',.:;!?")  # Nettoyer la ponctuation
            
            # Préserver les mots qui font partie des marques
            is_brand_word = any(brand_word.lower() == word_lower for brand_word in brand_words)
            
            if is_brand_word or word_lower not in self.FILLER_WORDS:
                result_words.append(word)
                
        return " ".join(result_words)
    
    def _reduce_brands_if_needed(self, title: str, max_length: int) -> str:
        """Réduire le nombre de marques si le titre est encore trop long"""
        if len(title) <= max_length:
            return title

        # Séparer le titre en parties
        parts = title.split()
        if len(parts) < 4:  # Pas assez de parties à optimiser
            return title

        # Trouver où commencent les marques (après le type d'appareil)
        reduced_title = self._safe_find_and_reduce_brands(parts)
        if reduced_title:
            return reduced_title

        return title[:max_length]  # Troncature brute en dernier recours

    @handle_seo_generation_errors()
    def _safe_find_and_reduce_brands(self, parts: list) -> str:
        """Trouver l'index 'pour' et réduire les marques de manière sécurisée"""
        # Format: "référence description pour type marque1 marque2 marque3"
        if "pour" not in parts:
            return None
        type_index = parts.index("pour") + 1  # Position du type d'appareil
        if type_index + 1 < len(parts):  # Il y a des marques après le type
            # Garder le titre jusqu'au type + une seule marque
            reduced_title = " ".join(parts[:type_index + 2])  # référence + desc + pour + type + 1 marque
            return reduced_title
        return None
    
    def _smart_truncate_with_brands(self, title: str, required_brands: str, max_length: int) -> str:
        """Troncature intelligente en essayant de garder au moins une marque"""
        if len(title) <= max_length:
            return title
            
        # Si même avec toutes les optimisations c'est trop long, tronquer intelligemment
        # Essayer de garder au moins la première marque
        brand_words = required_brands.split() if required_brands else []
        if brand_words:
            first_brand = brand_words[0]
            # Trouver la position de la première marque et garder jusqu'à elle
            if first_brand in title:
                brand_pos = title.find(first_brand)
                brand_end = brand_pos + len(first_brand)
                if brand_end <= max_length:
                    return title[:brand_end]
        
        # Troncature brute
        return title[:max_length]

    def _select_fabricants_for_description(self, fabricants: List[str], template: str,
                                         reference: str, description: str, type_appareil: str, 
                                         max_length: int) -> str:
        """Sélectionner le maximum de fabricants possibles dans un ordre aléatoire pour la description"""
        if not fabricants:
            return ""
        
        # Estimer la longueur de base du template
        base_length = len(template) - len("{description}") - len("{reference}") - len("{type_appareil}") - len("{fabricants}")
        base_length += len(description) + len(reference) + len(type_appareil)
        
        available_space = max_length - base_length
        
        if available_space <= 0:
            return ""
        
        # Dédupliquer en préservant l'ordre de fréquence (trié par seo_service, plus présents d'abord)
        seen: set = set()
        unique_fabricants = []
        for f in fabricants:
            f_clean = f.strip() if isinstance(f, str) else f
            if f_clean and f_clean not in seen:
                seen.add(f_clean)
                unique_fabricants.append(f_clean)
        
        # Construire la liste des fabricants selon l'espace disponible
        result_fabricants = []
        current_length = 0
        
        for i, fabricant in enumerate(unique_fabricants):
            fabricant_clean = fabricant.strip()
            needed_length = len(fabricant_clean) if i == 0 else len(" " + fabricant_clean)  # Espace au lieu de virgule-espace
            
            if current_length + needed_length <= available_space:
                result_fabricants.append(fabricant_clean)
                current_length += needed_length
            else:
                break
        
        if not result_fabricants:
            first_fabricant = unique_fabricants[0][:available_space]
            return first_fabricant if len(first_fabricant) > 0 else ""
        
        result_str = " ".join(result_fabricants)  # Espaces au lieu de virgules, sans ...
            
        return result_str
    
    def _smart_truncate_description(self, description: str, max_length: int) -> str:
        """Troncature intelligente pour la description (sans ellipse)"""
        if len(description) <= max_length:
            return description
        
        # Tronquer au dernier mot complet avant la limite
        truncated = description[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > 0:
            truncated = truncated[:last_space]
        
        return truncated  # Sans "..." pour gagner 3 caractères
    
    def get_random_description_variant(self, reference: str, description: str,
                                     type_appareil: str, fabricants: List[str],
                                     max_length: int = 150,
                                     ref_obsolete: Optional[str] = None,
                                     n_modeles: int = 0) -> Dict[str, any]:
        """Générer une nouvelle variante aléatoire de description"""
        return self.generate_meta_description(
            reference, description, type_appareil, fabricants, max_length, ref_obsolete, n_modeles
        )
    
    def _get_article(self, description: str) -> str:
        """
        Détermine l'article approprié (votre/vos) selon la description
        Inspiré de la fonction getArticle() du script.js
        """
        # Diviser la description en mots
        first_word = description.split(' ')[0] if description else ""
        
        # Vérifier si c'est probablement au pluriel
        is_plural = (
            first_word.endswith('s') or 
            first_word.endswith('x') or
            first_word.startswith('des ') or
            'pompes' in description.lower() or
            'joints' in description.lower() or
            'filtres' in description.lower() or
            'pièces' in description.lower()
        )
        
        return 'vos' if is_plural else 'votre'
    
    def get_last_generation_info(self) -> Dict[str, any]:
        """Récupérer les informations de la dernière génération"""
        return self.last_generation_info