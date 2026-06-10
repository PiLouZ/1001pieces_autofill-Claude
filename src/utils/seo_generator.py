"""
Module de génération de métadonnées SEO
Inspiré du script.js pour e-commerce pièces détachées électroménager
"""

import random
from typing import List, Dict, Tuple, Optional
from .error_handler import handle_seo_generation_errors

class SEOGenerator:
    """Générateur de métadonnées SEO pour pièces détachées électroménager"""
    
    # Pool unique de méta descriptions (18 templates — angles variés)
    META_DESCRIPTION_TEMPLATES = [
        # Achat direct
        "Commandez {description} {reference} pour {type_appareil} {fabricants} chez votre spécialiste pièces détachées",
        "Achetez {description} {reference} pour {type_appareil} {fabricants} — livraison rapide, retour facile",
        "Trouvez {description} {reference} pour {type_appareil} {fabricants} chez un expert de la réparation électroménager",
        "Découvrez {description} {reference} pour {type_appareil} {fabricants} chez le spécialiste de la pièce détachée",
        # Réparation
        "Réparez votre {type_appareil} {fabricants} avec {description} {reference} — commandez en ligne, livraison rapide",
        "Retrouvez {description} {reference} pour {type_appareil} {fabricants} et réparez votre appareil vous-même",
        "Redonnez vie à un {type_appareil} {fabricants} avec {description} {reference} — pièce disponible immédiatement",
        # Stock / disponibilité
        "{description_cap} {reference} pour {type_appareil} {fabricants} — pièce d'origine, expédition rapide",
        "{description_cap} {reference} en stock pour {type_appareil} {fabricants} — commandez chez votre spécialiste électroménager",
        "{description_cap} {reference} — pièce détachée disponible pour {type_appareil} {fabricants}, expédition rapide",
        # Question / besoin
        "En panne ? {description_cap} {reference} pour {type_appareil} {fabricants} est disponible chez votre réparateur agréé",
        "Besoin de {description} {reference} pour {type_appareil} {fabricants} ? Trouvez cette pièce chez votre spécialiste",
        "Votre {type_appareil} {fabricants} en panne ? Commandez {description} {reference} — la bonne pièce, livrée rapidement",
        "Panne sur votre {type_appareil} {fabricants} ? Commandez {description} {reference} — expédition rapide",
        # Réparer plutôt que remplacer
        "Évitez le remplacement — commandez {description} {reference} pour {type_appareil} {fabricants} chez votre spécialiste",
        "Réparer plutôt que jeter : {description} {reference} pour {type_appareil} {fabricants} chez votre expert pièces détachées",
        # DIY
        "{description_cap} {reference} pour {type_appareil} {fabricants} — réparez facilement votre appareil sans faire appel à un technicien",
        "Faites-le vous-même : {description} {reference} pour {type_appareil} {fabricants}, la réparation à portée de main",
    ]

    # Templates spécifiques aux pièces remplacées (ref_old → ref_current)
    # {ref_old} = ancienne référence recherchée, {reference} = référence courante
    META_DESCRIPTION_SUPERSEDED_TEMPLATES = [
        "Vous cherchez {ref_old} ? La référence actuelle est {reference} — commandez {description} pour {type_appareil} {fabricants}",
        "Référence {ref_old} remplacée par {reference} — {description} pour {type_appareil} {fabricants} chez votre spécialiste",
        "L'ancienne réf. {ref_old} est désormais {reference} — trouvez {description} pour {type_appareil} {fabricants}",
        "Nouvelle référence {reference} (remplace {ref_old}) — {description} pour {type_appareil} {fabricants}, livraison rapide",
        "Vous recherchez {ref_old} ? Elle a été remplacée par {reference} — {description} pour {type_appareil} {fabricants}",
        "{ref_old} n'existe plus : commandez {description} sous la référence {reference} pour {type_appareil} {fabricants}",
        "La pièce {ref_old} est désormais référencée {reference} — {description} pour {type_appareil} {fabricants}, en stock",
        "Ancienne référence {ref_old}, nouvelle référence {reference} — {description} pour {type_appareil} {fabricants} chez votre spécialiste",
    ]
    
    # Templates méta titles (4 variantes — format normal)
    META_TITLE_TEMPLATES = [
        "{reference} {description} pour {type_appareil} {fabricants}",
        "{reference} — {description} {type_appareil} {fabricants}",
        "{type_appareil} {fabricants} — {description} {reference}",
        "Pièce {reference} — {description} {type_appareil} {fabricants}",
    ]

    # Templates méta titles pour pièces remplacées (3 variantes)
    META_TITLE_SUPERSEDED_TEMPLATES = [
        "{ref_old}→{reference} {description} {type_appareil} {fabricants}",
        "Réf. {ref_old}→{reference} — {description} {type_appareil} {fabricants}",
        "{description} {type_appareil} {fabricants} ({ref_old}→{reference})",
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

    # Remplacements pour raccourcir les titres trop longs (dernier recours avant troncature)
    # Ordre de priorité : gain de caractères décroissant
    WORD_REPLACEMENTS = {
        "lave-vaisselle": "lave-vais.",  # -6 caractères (LV trop cryptique pour le grand public)
        "sèche-linge": "sèche-ling.",   # -4 caractères
        "réfrigérateur": "frigo",       # -7 caractères (terme courant)
        "lave-linge": "lave-ling.",     # -3 caractères
        "congélateur": "congélo",       # -4 caractères (terme courant)
        "électroménager": "électromén.", # -3 caractères
        "électroménagers": "électromén.", # -4 caractères
        "aspirateur": "aspiro",         # -4 caractères
        "micro-ondes": "micro-onde",    # -1 caractère
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
        Choisit aléatoirement parmi META_TITLE_TEMPLATES (normal) ou
        META_TITLE_SUPERSEDED_TEMPLATES (supersession).
        """
        reference_clean = reference.strip()
        description_clean = self._adjust_first_char(description.strip(), upper=True)
        type_clean = self._normalize_type(type_appareil)

        # ── Choisir le template selon le contexte ─────────────────────────────
        if ref_obsolete:
            template = random.choice(self.META_TITLE_SUPERSEDED_TEMPLATES)
            template_kwargs = dict(
                reference=reference_clean,
                description=description_clean,
                type_appareil=type_clean,
                ref_old=ref_obsolete.strip(),
            )
        else:
            template = random.choice(self.META_TITLE_TEMPLATES)
            template_kwargs = dict(
                reference=reference_clean,
                description=description_clean,
                type_appareil=type_clean,
            )

        fabricants_optimaux = self._maximize_brands_in_title(
            fabricants, template, max_length, **template_kwargs
        )

        raw_title = template.format(fabricants=fabricants_optimaux, **template_kwargs).strip()
        base_title = raw_title
        if len(raw_title) > max_length:
            base_title = self._optimize_title_with_brands(raw_title, fabricants_optimaux, max_length)

        generation_info = {
            'template_used': template,
            'original_length': len(raw_title),
            'final_length': len(base_title),
            'truncated': len(base_title) < len(raw_title),
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
        else:
            template = random.choice(self.META_DESCRIPTION_TEMPLATES)

        fabricants_str = self._select_fabricants_for_description(
            fabricants, template, reference_clean, description_with_article, type_clean, max_length,
            ref_old=ref_obsolete
        )

        # ── Instancier le template ────────────────────────────────────────────
        fmt_kwargs = dict(
            description=description_with_article,
            description_cap=self._adjust_first_char(description_with_article, upper=True),
            reference=reference_clean,
            type_appareil=type_clean,
            fabricants=fabricants_str,
        )
        if ref_obsolete:
            fmt_kwargs['ref_old'] = ref_obsolete.strip()

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
    
    def _maximize_brands_in_title(self, fabricants: List[str], template: str,
                                max_length: int, **template_kwargs) -> str:
        """Maximiser le nombre de marques dans le titre selon le template choisi"""
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

        # Calculer l'espace disponible : longueur du template sans les marques
        base_length = len(template.format(fabricants="", **template_kwargs))
        available_space = max_length - base_length

        # Construire la liste des marques optimale
        selected_brands = []
        current_length = 0

        for brand in unique_fabricants:
            new_length = current_length + (1 if selected_brands else 0) + len(brand)
            if new_length <= available_space:
                selected_brands.append(brand)
                current_length = new_length
            elif selected_brands:
                break
            else:
                # Même la première marque déborde — on la prend quand même (garantie de présence)
                selected_brands.append(brand)
                break

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
        optimized_title = self._reduce_brands_if_needed(optimized_title, max_length, required_brands)

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
    
    def _reduce_brands_if_needed(self, title: str, max_length: int, required_brands: str = "") -> str:
        """Réduire à une seule marque si le titre contient plusieurs marques et est encore trop long"""
        if len(title) <= max_length or not required_brands:
            return title

        brands = [b for b in required_brands.split() if b]
        if len(brands) <= 1:
            return title  # Une seule marque déjà — rien à réduire

        # Garder uniquement la première marque : localiser sa position dans le titre
        first_brand = brands[0]
        pos = title.find(first_brand)
        if pos >= 0:
            candidate = title[:pos + len(first_brand)].strip()
            if candidate:
                return candidate

        return title
    
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
                                         reference: str, description_with_article: str,
                                         type_appareil: str, max_length: int,
                                         ref_old: Optional[str] = None) -> str:
        """Sélectionner le maximum de fabricants possibles pour la description"""
        if not fabricants:
            return ""

        # Calculer l'espace disponible : rendu du template sans les marques, avec les vraies valeurs
        description_cap = self._adjust_first_char(description_with_article, upper=True)
        fmt_kwargs = dict(
            description=description_with_article,
            description_cap=description_cap,
            reference=reference,
            type_appareil=type_appareil,
            fabricants="",
        )
        if ref_old:
            fmt_kwargs['ref_old'] = ref_old
        base_length = len(template.format(**fmt_kwargs))
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
            needed_length = len(fabricant_clean) if i == 0 else len(" " + fabricant_clean)

            if current_length + needed_length <= available_space:
                result_fabricants.append(fabricant_clean)
                current_length += needed_length
            else:
                break

        if not result_fabricants:
            first_fabricant = unique_fabricants[0][:available_space]
            return first_fabricant if first_fabricant else ""

        return " ".join(result_fabricants)
    
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

    def get_random_title_variant(self, reference: str, description: str,
                                type_appareil: str, fabricants: List[str],
                                max_length: int = 60,
                                ref_obsolete: Optional[str] = None) -> Dict[str, any]:
        """Générer une nouvelle variante aléatoire de méta title"""
        return self.generate_meta_title(
            reference, description, type_appareil, fabricants, max_length, ref_obsolete
        )
    
    def _get_article(self, description: str) -> str:
        """
        Détermine l'article possessif (votre/vos) selon la description.
        Détecte le pluriel via des signaux explicites uniquement — évite les faux positifs
        sur les mots singuliers finissant par 's' ou 'x' (sonde, soupape, flux, corps…).
        """
        if not description:
            return 'votre'
        desc_lower = description.lower()
        first_word = desc_lower.split()[0]

        is_plural = (
            desc_lower.startswith('des ') or              # article indéfini pluriel explicite
            first_word[0].isdigit() or                    # "3 joints", "2 filtres"
            any(w in desc_lower for w in [                # mots spécifiquement pluriels
                'pompes', 'joints', 'filtres', 'pièces',
                'écrous', 'roulements', 'ressorts', 'brosses',
                'clips', 'courroies', 'lames', 'plaques',
            ])
        )

        return 'vos' if is_plural else 'votre'
    
    def get_last_generation_info(self) -> Dict[str, any]:
        """Récupérer les informations de la dernière génération"""
        return self.last_generation_info