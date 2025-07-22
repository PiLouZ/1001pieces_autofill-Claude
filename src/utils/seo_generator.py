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
    
    # Remplacements pour raccourcir (comme dans script.js)
    WORD_REPLACEMENTS = {
        "électroménager": "électromén.",
        "électroménagers": "électromén.",
        "réfrigérateur": "frigo",
        "lave-vaisselle": "LV",
        "lave-linge": "LL",
        "sèche-linge": "SL",
        "micro-ondes": "micro-onde"
    }
    
    def __init__(self):
        self.last_generation_info = {}
    
    def generate_meta_title(self, reference: str, description: str, type_appareil: str, 
                           fabricants: List[str], max_length: int = 60) -> Dict[str, any]:
        """
        Générer un méta title optimisé
        Format: [Référence pièce] - [Description pièce] pour [type appareil] [Fabricant]
        """
        try:
            # Nettoyer et formater les données
            reference_clean = reference.strip()
            description_clean = description.strip().capitalize()
            type_clean = type_appareil.strip().lower()
            
            # Sélectionner les fabricants selon l'espace disponible
            fabricants_str = self._select_fabricants_for_title(fabricants, reference_clean, 
                                                              description_clean, type_clean, max_length)
            
            # Construire le titre de base
            base_title = f"{reference_clean} - {description_clean} pour {type_clean} {fabricants_str}"
            
            # Si le titre est trop long, essayer sans " - " pour gagner 3 caractères
            if len(base_title) > max_length:
                compact_title = f"{reference_clean} {description_clean} pour {type_clean} {fabricants_str}"
                if len(compact_title) <= max_length:
                    base_title = compact_title
            
            # Appliquer la troncature intelligente si nécessaire
            final_title = self._smart_truncate_title(base_title, max_length)
            
            # Informations de génération
            generation_info = {
                'original_length': len(base_title),
                'final_length': len(final_title),
                'truncated': len(final_title) < len(base_title),
                'within_limit': len(final_title) <= max_length,
                'fabricants_used': fabricants_str,
                'fabricants_count': len(fabricants)
            }
            
            self.last_generation_info['title'] = generation_info
            
            return {
                'title': final_title,
                'length': len(final_title),
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
        """Troncature intelligente pour le titre (inspiré du script.js)"""
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