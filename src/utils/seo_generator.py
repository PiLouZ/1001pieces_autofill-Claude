"""
Module de génération de métadonnées SEO
Inspiré du script.js pour e-commerce pièces détachées électroménager
"""

import random
from typing import List, Dict, Tuple, Optional

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
        "Découvrez {description} {reference} pour {type_appareil} {fabricants} chez votre spécialiste pièces détachées"
    ]
    
    # Mots à exclure pour optimiser la longueur (comme dans script.js)
    EXCLUDED_WORDS = [
        "électroménager", "électroménagers", "appareils", "appareil", 
        "pièces", "pièce", "détachées", "détachée", "de", "du", "des", "la", "le", "les"
    ]
    
    # Mots de liaison à supprimer en priorité pour préserver les marques
    FILLER_WORDS = [
        "pour", "de", "des", "du", "la", "le", "les", "d'", "l'",
        "avec", "sans", "sur", "sous", "dans", "par", "et"
    ]
    
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
    
    def generate_meta_title(self, reference: str, description: str, type_appareil: str, 
                           fabricants: List[str], max_length: int = 60) -> Dict[str, any]:
        """
        Générer un méta title optimisé avec priorité à l'inclusion d'au moins 1 marque
        Format: [Référence pièce] - [Description pièce] pour [type appareil] [Fabricant]
        """
        try:
            # Nettoyer et formater les données
            reference_clean = reference.strip()
            description_clean = description.strip().capitalize()
            type_clean = type_appareil.strip().lower()
            
            # Étape 1: Maximiser le nombre de marques pour atteindre ~60 caractères
            fabricants_optimaux = self._maximize_brands_in_title(fabricants, reference_clean, 
                                                               description_clean, type_clean, max_length)
            
            # Construire le titre de base avec le maximum de fabricants possible
            base_title = f"{reference_clean} - {description_clean} pour {type_clean} {fabricants_optimaux}"
            
            # Étape 2: Optimiser si le titre dépasse 60 caractères
            if len(base_title) > max_length:
                # Essayer sans " - " (gagne 3 caractères)
                compact_title = f"{reference_clean} {description_clean} pour {type_clean} {fabricants_optimaux}"
                if len(compact_title) <= max_length:
                    base_title = compact_title
                else:
                    # Appliquer les optimisations intelligentes tout en gardant les marques
                    base_title = self._optimize_title_with_brands(compact_title, fabricants_optimaux, max_length)
            
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
                'brand_guaranteed': bool(fabricants_optimaux.strip())
            }
            
            self.last_generation_info['title'] = generation_info
            
            return {
                'title': base_title,
                'length': len(base_title),
                'info': generation_info
            }
            
        except Exception as e:
            return {
                'title': f"Erreur génération titre: {e}",
                'length': 0,
                'info': {'error': str(e)}
            }
    
    def generate_meta_description(self, reference: str, description: str, type_appareil: str,
                                 fabricants: List[str], max_length: int = 150) -> Dict[str, any]:
        """
        Générer une méta description aléatoire
        Format: [Phrase] {description} {reference} pour {type appareil} {fabricants} [phrase]
        """
        try:
            # Nettoyer et formater les données  
            reference_clean = reference.strip()
            description_clean = description.strip().lower()
            type_clean = type_appareil.strip().lower()
            
            # Ajouter l'article approprié (votre/vos) devant la description
            article = self._get_article(description_clean)
            description_with_article = f"{article} {description_clean}"
            
            # Sélectionner un template aléatoire
            template = random.choice(self.META_DESCRIPTION_TEMPLATES)
            
            # Sélectionner les fabricants selon l'espace disponible
            fabricants_str = self._select_fabricants_for_description(fabricants, template,
                                                                   reference_clean, description_clean, 
                                                                   type_clean, max_length)
            
            # Construire la description
            description_text = template.format(
                description=description_with_article,
                reference=reference_clean,
                type_appareil=type_clean,
                fabricants=fabricants_str
            )
            
            # Appliquer la troncature intelligente si nécessaire
            final_description = self._smart_truncate_description(description_text, max_length)
            
            # Informations de génération
            generation_info = {
                'template_used': template,
                'original_length': len(description_text),
                'final_length': len(final_description),
                'truncated': len(final_description) < len(description_text),
                'within_limit': len(final_description) <= max_length,
                'fabricants_used': fabricants_str,
                'fabricants_count': len(fabricants)
            }
            
            self.last_generation_info['description'] = generation_info
            
            return {
                'description': final_description,
                'length': len(final_description),
                'info': generation_info
            }
            
        except Exception as e:
            return {
                'description': f"Erreur génération description: {e}",
                'length': 0,
                'info': {'error': str(e)}
            }
    
    def _maximize_brands_in_title(self, fabricants: List[str], reference: str, 
                                description: str, type_appareil: str, max_length: int) -> str:
        """Maximiser le nombre de marques dans le titre pour atteindre ~60 caractères"""
        if not fabricants:
            return ""
        
        # Dédupliquer et trier les fabricants par longueur (plus courts d'abord pour en avoir plus)
        unique_fabricants = list(set(f.strip() for f in fabricants if f.strip()))
        unique_fabricants.sort(key=len)  # Marques courtes d'abord
        
        # Calculer l'espace disponible pour les marques
        base_without_brands = f"{reference} - {description} pour {type_appareil} "
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
        try:
            # Format: "référence description pour type marque1 marque2 marque3"
            type_index = parts.index("pour") + 1  # Position du type d'appareil
            if type_index + 1 < len(parts):  # Il y a des marques après le type
                # Garder le titre jusqu'au type + une seule marque
                reduced_title = " ".join(parts[:type_index + 2])  # référence + desc + pour + type + 1 marque
                return reduced_title
        except ValueError:
            pass  # Si structure inattendue, continuer avec la troncature normale
            
        return title[:max_length]  # Troncature brute en dernier recours
    
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

    def _select_fabricants_for_title(self, fabricants: List[str], reference: str, 
                                   description: str, type_appareil: str, max_length: int) -> str:
        """Sélectionner le maximum de fabricants possibles dans un ordre aléatoire pour le titre"""
        if not fabricants:
            return ""
        
        # Calculer l'espace disponible pour les fabricants
        base_format = f"{reference} - {description} pour {type_appareil} "
        available_space = max_length - len(base_format)
        
        if available_space <= 0:
            return ""
        
        # Mélanger les fabricants de façon aléatoire et supprimer les doublons
        unique_fabricants = list(set(fabricants))
        random.shuffle(unique_fabricants)
        
        # Construire la liste des fabricants selon l'espace disponible
        result_fabricants = []
        current_length = 0
        
        for i, fabricant in enumerate(unique_fabricants):
            fabricant_clean = fabricant.strip()
            if i == 0:
                needed_length = len(fabricant_clean)
            else:
                needed_length = len(" " + fabricant_clean)  # Espace au lieu de virgule-espace
            
            if current_length + needed_length <= available_space:
                result_fabricants.append(fabricant_clean)
                current_length += needed_length
            else:
                break
        
        if not result_fabricants:
            # Au moins essayer de mettre le premier fabricant même tronqué (sans ...)
            first_fabricant = unique_fabricants[0][:available_space]
            return first_fabricant if len(first_fabricant) > 0 else ""
        
        # Pas de "..." - juste utiliser l'espace au maximum
        result_str = " ".join(result_fabricants)  # Espaces au lieu de virgules
        
        return result_str
    
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
        
        # Mélanger les fabricants de façon aléatoire et supprimer les doublons
        unique_fabricants = list(set(fabricants))
        random.shuffle(unique_fabricants)
        
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
    
    def _smart_truncate_title(self, title: str, max_length: int) -> str:
        """Troncature intelligente pour le titre"""
        if len(title) <= max_length:
            return title
        
        # D'abord, essayer de supprimer les mots exclus
        words = title.split()
        for excluded_word in self.EXCLUDED_WORDS:
            while len(" ".join(words)) > max_length and excluded_word in [w.lower() for w in words]:
                # Trouver et supprimer le premier mot exclu
                for i, word in enumerate(words):
                    if word.lower() == excluded_word.lower():
                        words.pop(i)
                        break
        
        # Ensuite, appliquer les remplacements
        current_title = " ".join(words)
        for original, replacement in self.WORD_REPLACEMENTS.items():
            if original in current_title.lower() and len(current_title) > max_length:
                current_title = current_title.replace(original, replacement)
                current_title = current_title.replace(original.capitalize(), replacement)
        
        # Si toujours trop long, tronquer sans ellipse (gagner 3 chars)
        if len(current_title) > max_length:
            current_title = current_title[:max_length]
        
        return current_title
    
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
                                     max_length: int = 150) -> Dict[str, any]:
        """Générer une nouvelle variante aléatoire de description"""
        return self.generate_meta_description(reference, description, type_appareil, fabricants, max_length)
    
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