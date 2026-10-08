"""
Module de génération de métadonnées SEO
Inspiré du script.js pour e-commerce pièces détachées électroménager
"""

import random
import zlib
from typing import List, Dict, Tuple, Optional
from .error_handler import handle_seo_generation_errors
from .largeur_texte import largeur_px, TAILLE_TITLE_PX, TAILLE_DESCRIPTION_PX

class SEOGenerator:
    """Générateur de métadonnées SEO pour pièces détachées électroménager"""
    
    # Pool unique de méta descriptions (25 templates — angles variés)
    META_DESCRIPTION_TEMPLATES = [
        # Achat direct
        "Commandez {description} {reference} pour {type_appareil} {fabricants} chez votre spécialiste pièces détachées",
        "Achetez {description} {reference} pour {type_appareil} {fabricants} — livraison à domicile ou retrait en magasin",
        "Trouvez {description} {reference} pour {type_appareil} {fabricants} chez un expert de la réparation électroménager",
        "Découvrez {description} {reference} pour {type_appareil} {fabricants} chez le spécialiste de la pièce détachée",
        # Réparation
        "Réparez votre {type_appareil} {fabricants} avec {description} {reference} — commandez en ligne, livraison rapide",
        "Retrouvez {description} {reference} pour {type_appareil} {fabricants} et réparez votre appareil vous-même",
        "Redonnez vie à un {type_appareil} {fabricants} avec {description} {reference} — commande en ligne, expédition rapide",
        # Expédition / qualité (aucune donnée de stock : jamais « en stock » ni « disponible »)
        "{description_cap} {reference} pour {type_appareil} {fabricants} — d'origine ou de qualité équivalente, expédition rapide",
        "{description_cap} {reference} pour {type_appareil} {fabricants} — commandez chez votre spécialiste électroménager",
        "{description_cap} {reference} — pièce détachée pour {type_appareil} {fabricants}, expédition rapide",
        # Question / besoin
        "En panne ? {description_cap} {reference} pour {type_appareil} {fabricants} — livraison ou retrait en magasin",
        "Besoin de {description} {reference} pour {type_appareil} {fabricants} ? Trouvez cette pièce chez votre spécialiste",
        "Votre {type_appareil} {fabricants} en panne ? Commandez {description} {reference} — la bonne pièce, livrée rapidement",
        "Panne sur votre {type_appareil} {fabricants} ? Commandez {description} {reference} — expédition rapide",
        # Réparer plutôt que remplacer
        "Évitez le remplacement — commandez {description} {reference} pour {type_appareil} {fabricants} chez votre spécialiste",
        "Réparer plutôt que jeter : {description} {reference} pour {type_appareil} {fabricants} chez votre expert pièces détachées",
        # DIY
        "{description_cap} {reference} pour {type_appareil} {fabricants} — commandez la pièce, réparez votre appareil",
        "Faites-le vous-même : {description} {reference} pour {type_appareil} {fabricants}, la réparation à portée de main",
        # Qualité pièce : d'origine OU équivalente, jamais « d'origine » seul (pas de donnée par pièce),
        # jamais « OEM » (jargon), pas de mention de garantie
        "{description_cap} {reference} pour {type_appareil} {fabricants} — pièce d'origine ou de qualité équivalente",
        # Retour (21 jours après réception, frais à la charge du client → wording factuel)
        "Commandez {description} {reference} pour {type_appareil} {fabricants} — retour possible sous 21 jours après réception",
        # Expédition le jour même (commande validée avant 15h en jour ouvré)
        "En panne ? {description_cap} {reference} pour {type_appareil} {fabricants} — commande avant 15h, expédition le jour même",
        # Livraison express Chronopost (le lendemain avant 13h)
        "{description_cap} {reference} pour {type_appareil} {fabricants} — livraison Chronopost dès le lendemain avant 13h",
        # Retrait en magasin (immédiat après validation de la commande)
        "{description_cap} {reference} pour {type_appareil} {fabricants} — à retirer en magasin dès la commande validée",
        # Livraison standard (La Poste, 48 à 72h en métropole)
        "Trouvez {description} {reference} pour {type_appareil} {fabricants} — livraison à domicile en 48 à 72h en métropole",
        # Écologie / économie (réparer plutôt que remplacer)
        "Économique et écologique : {description} {reference} pour {type_appareil} {fabricants}, réparez au lieu de remplacer",
    ]

    # ── L2 : templates contextuels (rejoignent le pool SEULEMENT si leur signal est actif) ──
    # Forte compatibilité : la pièce équipe beaucoup de modèles d'appareils différents.
    # {nb_modeles} = nombre de modèles compatibles arrondi vers le bas (« 1 200 ») :
    # propre à la fiche, et toujours vrai (décision client : données assez complètes
    # pour publier un chiffre). Remplace « compatible avec de nombreux {type} », qui
    # ne s'accordait pas (« de nombreux plaque ») dans 98 % des cas.
    META_DESCRIPTION_TEMPLATES_COMPAT = [
        "{description_cap} {reference} pour {type_appareil} {fabricants} — compatible avec plus de {nb_modeles} modèles",
        "Pièce multi-modèles : {description} {reference} pour {type_appareil} {fabricants}, compatible avec plus de {nb_modeles} modèles",
    ]
    # Supersession : la référence remplace d'anciennes références, que les clients
    # cherchent encore (c'est souvent celle imprimée sur la pièce usée). Quand il y
    # en a, la description les cite TOUJOURS : ces gabarits forment alors le pool.
    # {anciennes_refs} = « ancienne réf. X » ou « anciennes réf. X et Y » : forme
    # nominale, qui s'accorde avec tout libellé (« vos filtres … remplace » était faux).
    # Depuis la 3.77.0, il porte aussi les réfs équivalentes (« réf. équivalente Z »,
    # cf. _formuler_refs_liees) : mêmes gabarits, toujours cités eux aussi.
    META_DESCRIPTION_TEMPLATES_SUPERSESSION = [
        "{description_cap} {reference} pour {type_appareil} {fabricants} — {anciennes_refs}",
        "{description_cap} {reference} ({anciennes_refs}) pour {type_appareil} {fabricants}",
        "{description_cap} {reference} pour {type_appareil} {fabricants}, {anciennes_refs} — Chronopost J+1 avant 13h",
        "{description_cap} {reference} ({anciennes_refs}) pour {type_appareil} {fabricants} — commande avant 15h, expédition le jour même",
        "Pièce détachée {type_appareil} {fabricants} : {description} {reference}, {anciennes_refs}",
        "{description_cap} {reference} ({anciennes_refs}) pour {type_appareil} {fabricants} — retrait en magasin possible",
    ]
    # Anciennes références citées au plus (les plus compatibles, choisies par seo_service)
    MAX_ANCIENNES_REFS = 2
    # Réfs équivalentes (autres marques, hors chaîne) citées au plus — décision client
    # 2026-10-08 : 2 au plus, et 1 ancienne + 1 équivalente quand la fiche a les deux.
    MAX_EQUIVALENTES = 2
    # Seuil « large compatibilité » (nb de modèles) et poids des templates contextuels
    # dans le tirage pondéré. Réglables : un poids > 1 favorise sans forcer (la diversité
    # du pool générique reste possible).
    COMPAT_MODELS_THRESHOLD = 20
    CONTEXT_TEMPLATE_WEIGHT = 6.0

    # ── L3 : templates par segment d'appareil ──
    # L'appareil et ses marques en tête (« Lave-linge Candy : … »), comme dans les
    # recherches « pièce lave-linge candy ». Pas d'accroche symptôme (« Ne vidange
    # plus ? ») : choisie selon l'appareil et non la pièce, elle tombait le plus souvent
    # à côté (sur un verrou, un joint…) et ressemblait à un conseil de diagnostic,
    # que le SAV ne fournit pas (décision client 2026-09-24).
    # Clés = sortie de _normalize_type(). Matching par clé la plus longue contenue
    # (via _segment_templates_for) pour gérer "lave-linge top", "four micro-ondes".
    # Fallback systématique sur le pool générique si le type n'a pas d'entrée.
    SEGMENT_DESCRIPTION_TEMPLATES = {
        "lave-linge": [
            "Lave-linge {fabricants} : {description} {reference} — Chronopost J+1 avant 13h",
            "Pièce détachée {type_appareil} {fabricants} : {description} {reference}, commande avant 15h, expédition le jour même",
        ],
        "lave-vaisselle": [
            "Lave-vaisselle {fabricants} : {description} {reference} — commande avant 15h, expédition le jour même",
            "Pièce détachée {type_appareil} {fabricants} : {description} {reference}, retrait en magasin possible",
        ],
        "réfrigérateur": [
            "Réfrigérateur {fabricants} : {description} {reference} — Chronopost J+1 avant 13h",
            "Pièce détachée {type_appareil} {fabricants} : {description} {reference}, La Poste 48-72h en métropole",
        ],
        "sèche-linge": [
            "Sèche-linge {fabricants} : {description} {reference} — commande avant 15h, expédition le jour même",
            "Pièce détachée {type_appareil} {fabricants} : {description} {reference}, retour possible sous 21 jours",
        ],
        "four": [
            "Four {fabricants} : {description} {reference} — Chronopost J+1 avant 13h",
            "Pièce détachée {type_appareil} {fabricants} : {description} {reference}, retrait en magasin possible",
        ],
        "hotte": [
            "Hotte {fabricants} : {description} {reference} — retrait en magasin possible",
            "Pièce détachée {type_appareil} {fabricants} : {description} {reference}, commande avant 15h, expédition le jour même",
        ],
        "congélateur": [
            "Congélateur {fabricants} : {description} {reference} — La Poste 48-72h en métropole",
            "Pièce détachée {type_appareil} {fabricants} : {description} {reference}, Chronopost J+1 avant 13h",
        ],
        "micro-ondes": [
            "Micro-ondes {fabricants} : {description} {reference} — commande avant 15h, expédition le jour même",
            "Pièce détachée {type_appareil} {fabricants} : {description} {reference}, Chronopost J+1 avant 13h",
        ],
    }

    # Méta title — 2 gabarits, référence (courante) TOUJOURS en position 0 : elle
    # n'est jamais raccourcie. Le type d'appareil précède toujours les marques (un
    # 3ᵉ gabarit « … {fabricants} {type_appareil} » a été retiré : avec des virgules,
    # « Bosch, Siemens, Neff lave-vaisselle » rattachait l'appareil à la seule
    # dernière marque, et le type en fin de title était coupé en premier).
    # Les anciennes références ne sont pas mentionnées (décision produit).
    META_TITLE_TEMPLATES = [
        "{reference} {description} {type_appareil} {fabricants}",
        "{reference} {description} pour {type_appareil} {fabricants}",
    ]

    # Au plus 3 marques, séparées par des virgules (title : « A, B, C » ; description :
    # « A, B et C »). Au-delà, une liste de marques collées se lit comme du bourrage de
    # mots-clés et repousse les arguments commerciaux hors de l'affichage Google.
    MAX_MARQUES = 3

    # Noms de marque raccourcis dans les métas (décision client) ; la base garde le
    # nom complet. « Arthur-Martin-Electrolux » (24 car.) réduisait le title de la
    # carte 973914527609015 à « Carte lave-linge Arthur-Martin-Electrolux ».
    NOMS_COURTS_MARQUES = {
        "Arthur-Martin-Electrolux": "Arthur Martin",
    }

    # Limites de l'affichage Google sur ordinateur (décision client : régler sur
    # l'ordinateur ; sur mobile, seule la fin — l'argument commercial — est coupée).
    # Google coupe à la largeur en pixels (≈ 580 px / 920 px) : une marge de 5 et
    # 10 px absorbe les écarts de rendu. Le plafond en caractères reste un garde-fou.
    TITLE_MAX_PX = 575
    TITLE_MAX_CARACTERES = 65
    DESCRIPTION_MAX_PX = 910
    DESCRIPTION_MAX_CARACTERES = 155

    # Mots sur lesquels un libellé raccourci ne doit pas se terminer
    # (« Façade tiroir congélation intermédiaire ou » → « … intermédiaire »).
    MOTS_DE_LIAISON = {
        "à", "au", "aux", "avec", "d'", "de", "des", "du", "en", "et", "l'", "la",
        "le", "les", "ou", "par", "pour", "sans", "sous", "sur", "dans", "+", "-", "/", "&",
    }

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
                           fabricants: List[str], max_length: int = TITLE_MAX_CARACTERES,
                           variante: int = 0) -> Dict[str, any]:
        """
        Générer un méta title : référence (courante) en tête, puis libellé,
        type d'appareil et jusqu'à 3 marques, via un gabarit tiré de META_TITLE_TEMPLATES.

        S'il dépasse TITLE_MAX_PX ou max_length caractères, on essaie dans l'ordre,
        jusqu'à ce que ça tienne :
        retirer « pour », retirer des marques (3 → 2 → 1), raccourcir le libellé mot
        entier par mot entier (le type d'appareil est gardé : décision client), puis
        retirer le type. Jamais d'abréviation, jamais de mot ni de marque coupés ;
        au moins une marque tant qu'il y en a une.

        Le gabarit est fixe pour une référence donnée (voir _ordre_deterministe) ;
        `variante` > 0 passe aux formulations suivantes (Maj+clic dans l'interface).
        """
        reference_clean = reference.strip()
        description_clean = self._adjust_first_char(description.strip(), upper=True)
        type_clean = self._normalize_type(type_appareil)
        marques = self._marques_uniques(fabricants)[:self.MAX_MARQUES]

        template = self._choose_title_template(reference_clean, variante)
        title_complet = self._rendre_title(template, reference_clean, description_clean,
                                           type_clean, marques)
        title, marques_retenues = self._raccourcir_title(
            template, reference_clean, description_clean, type_clean, marques, max_length
        )
        fabricants_utilises = ", ".join(marques_retenues)

        generation_info = {
            'template_used': template,
            'original_length': len(title_complet),
            'final_length': len(title),
            'truncated': len(title) < len(title_complet),
            'within_limit': self._tient_title(title, max_length),
            'largeur_px': round(largeur_px(title, TAILLE_TITLE_PX)),
            'fabricants_used': fabricants_utilises,
            'fabricants_count': len(marques_retenues),
            'total_fabricants_available': len(fabricants),
            'brand_guaranteed': bool(marques_retenues),
            'variante': variante % len(self.META_TITLE_TEMPLATES),
            'nb_variantes': len(self.META_TITLE_TEMPLATES),
        }

        self.last_generation_info['title'] = generation_info

        return {
            'title': title,
            'length': len(title),
            'info': generation_info
        }

    def _choose_title_template(self, reference: str, variante: int = 0) -> str:
        gabarits = self.META_TITLE_TEMPLATES
        ordre = self._ordre_deterministe(gabarits, [1.0] * len(gabarits), reference)
        return ordre[variante % len(ordre)]

    @staticmethod
    def _ordre_deterministe(gabarits: List[str], poids: List[float], reference: str) -> List[str]:
        """
        Gabarits dans un ordre propre à la référence : tirage pondéré sans remise
        (clé = u ** (1/poids), méthode d'Efraimidis-Spirakis), avec un générateur
        initialisé par crc32(référence). Le premier suit donc la même loi que
        l'ancien tirage au hasard, mais une référence donne toujours le même : la
        méta est reproductible, et régénérer une fiche en ligne ne la change pas.
        Les suivants servent de formulations de rechange, sans répétition avant
        d'avoir fait le tour.
        crc32 et non hash() : hash() d'une chaîne change à chaque lancement de Python.
        Ajouter ou retirer un gabarit redistribue l'ordre de toutes les références.
        """
        rng = random.Random(zlib.crc32(reference.encode('utf-8')))
        cles = [rng.random() ** (1.0 / p) for p in poids]
        return [g for _, g in sorted(zip(cles, gabarits), key=lambda x: -x[0])]

    @classmethod
    def _marques_uniques(cls, fabricants: List[str]) -> List[str]:
        """
        Marques sans doublon ni vide, dans l'ordre reçu (classées par seo_service),
        sous leur nom court pour les métas (NOMS_COURTS_MARQUES).
        """
        vues: set = set()
        marques = []
        for f in fabricants:
            f = f.strip() if isinstance(f, str) else f
            f = cls.NOMS_COURTS_MARQUES.get(f, f)
            if f and f not in vues:
                vues.add(f)
                marques.append(f)
        return marques

    @staticmethod
    def _rendre_title(template: str, reference: str, description: str,
                      type_appareil: str, marques: List[str]) -> str:
        # " ".join(split()) : un champ vide ne laisse pas de double espace
        return " ".join(template.format(reference=reference, description=description,
                                        type_appareil=type_appareil,
                                        fabricants=", ".join(marques)).split())

    def _raccourcir_title(self, template: str, reference: str, description: str,
                          type_appareil: str, marques: List[str],
                          max_length: int) -> Tuple[str, List[str]]:
        """Première version du title qui tient (voir generate_meta_title)."""
        sans_pour = template.replace(" pour ", " ")
        gabarits = [template] if sans_pour == template else [template, sans_pour]
        paliers = [marques[:n] for n in range(len(marques), 0, -1)] or [[]]

        # 1-2. « pour », puis le nombre de marques
        for marques_n in paliers:
            for gabarit in gabarits:
                title = self._rendre_title(gabarit, reference, description, type_appareil, marques_n)
                if self._tient_title(title, max_length):
                    return title, marques_n

        # 3. Libellé raccourci mot entier par mot entier, type et 1 marque gardés
        marques_1 = paliers[-1]
        for libelle in self._libelles_raccourcis(description):
            title = self._rendre_title(sans_pour, reference, libelle, type_appareil, marques_1)
            if self._tient_title(title, max_length):
                return title, marques_1

        # 4. Sans le type d'appareil
        sans_type = sans_pour.replace("{type_appareil}", "")
        for libelle in [description] + self._libelles_raccourcis(description):
            title = self._rendre_title(sans_type, reference, libelle, type_appareil, marques_1)
            if self._tient_title(title, max_length):
                return title, marques_1

        # 5. Dernier recours : retirer des mots entiers à la fin (marque trop longue)
        coupe = self._rendre_title(sans_type, reference, "", type_appareil, marques_1)
        while not self._tient_title(coupe, max_length) and " " in coupe:
            coupe = coupe.rsplit(" ", 1)[0].rstrip(",")
        return coupe, [m for m in marques_1 if m in coupe]

    def _tient_title(self, title: str, max_length: int) -> bool:
        return (len(title) <= max_length
                and largeur_px(title, TAILLE_TITLE_PX) <= self.TITLE_MAX_PX)

    def _tient_description(self, texte: str, max_length: int) -> bool:
        return (len(texte) <= max_length
                and largeur_px(texte, TAILLE_DESCRIPTION_PX) <= self.DESCRIPTION_MAX_PX)

    def _libelles_raccourcis(self, libelle: str) -> List[str]:
        """
        Versions du libellé de plus en plus courtes, en retirant un mot entier à la
        fois. Aucune ne se termine sur un mot de liaison ni ne laisse de parenthèse
        ouverte ; le premier mot est toujours gardé.
        """
        mots = libelle.split()
        versions = []
        for n in range(len(mots) - 1, 0, -1):
            garde = mots[:n]
            while len(garde) > 1 and (garde[-1].lower() in self.MOTS_DE_LIAISON
                                      or garde[-1].lower().endswith(("'", "’"))):
                garde = garde[:-1]
            texte = " ".join(garde).rstrip(",;:-")
            if texte.count("(") > texte.count(")"):
                texte = texte[:texte.rindex("(")].rstrip(" ,;:-")
            if texte and texte not in versions:
                versions.append(texte)
        return versions

    @handle_seo_generation_errors()
    def generate_meta_description(self, reference: str, description: str, type_appareil: str,
                                 fabricants: List[str], max_length: int = DESCRIPTION_MAX_CARACTERES,
                                 n_modeles: int = 0, anciennes_refs: Optional[List[str]] = None,
                                 variante: int = 0,
                                 equivalentes: Optional[List[str]] = None) -> Dict[str, any]:
        """
        Générer une méta description via un tirage pondéré contextuel (L2/L3) :
        pool générique (unicité à grande échelle) enrichi de templates de segment
        (type d'appareil) et de forte compatibilité (n_modeles), favorisés sans jamais
        évincer la diversité générique.
        La référence est la référence courante (résolue en amont). anciennes_refs, si
        fourni, liste les références qu'elle remplace, les plus pertinentes d'abord :
        les MAX_ANCIENNES_REFS premières sont alors toujours citées (une seule si les
        deux ne laissent la place à aucune marque).
        equivalentes, si fourni, liste ses réfs équivalentes hors chaîne (autres
        marques), les plus pertinentes d'abord : MAX_EQUIVALENTES citées au plus.
        Avec les deux à la fois : 1 ancienne + 1 équivalente (décision client).
        Le gabarit est fixe pour une référence donnée (voir _ordre_deterministe) ;
        `variante` > 0 passe aux formulations suivantes (Maj+clic dans l'interface).
        """
        reference_clean = reference.strip()
        description_clean = self._adjust_first_char(description.strip(), upper=False)
        type_clean = self._normalize_type(type_appareil)
        anciennes = [r.strip() for r in (anciennes_refs or []) if r and r.strip()]
        anciennes = anciennes[:self.MAX_ANCIENNES_REFS]
        equivs = [r.strip() for r in (equivalentes or []) if r and r.strip()]
        equivs = equivs[:self.MAX_EQUIVALENTES]
        if anciennes and equivs:
            anciennes, equivs = anciennes[:1], equivs[:1]
        a_des_refs_liees = bool(anciennes or equivs)

        article = self._get_article(description_clean)
        description_with_article = f"{article} {description_clean}"

        template = self._choose_description_template(type_clean, n_modeles, a_des_refs_liees,
                                                     reference_clean, variante)
        pool, poids = self._pool_description(type_clean, n_modeles, a_des_refs_liees)
        nb_variantes = len(pool)
        a_des_marques = bool(self._marques_uniques(fabricants))

        # Le gabarit prévu, puis, s'il ne laisse la place à aucune marque ou oblige à
        # couper la phrase (« … compatible avec plus de 200 »), les suivants dans
        # l'ordre propre à la référence : le résultat reste fixe pour une référence.
        ordre = self._ordre_deterministe(pool, poids, reference_clean)
        depart = ordre.index(template) if template in ordre else 0
        candidats = [template] + [ordre[(depart + k) % len(ordre)] for k in range(1, len(ordre))
                                  if ordre[(depart + k) % len(ordre)] != template]
        # Avec des équivalentes, un 1er passage n'accepte qu'un gabarit qui garde TOUTES
        # les réfs prévues : sinon le repli (une seule réf liée) sacrifierait
        # l'équivalente dès le gabarit prévu, alors qu'un suivant tient en entier
        # (34 fiches sur 329 au 2026-10-08). Sans équivalente : un seul passage, comme
        # avant — les métas existantes restent identiques au caractère près.
        nb_prevu = len(anciennes) + len(equivs)
        exigences = (True, False) if equivs else (False,)
        premier = choisi = None
        rendus = {}
        for toutes_les_refs in exigences:
            for candidat in candidats:
                if candidat not in rendus:
                    rendus[candidat] = self._remplir_description(
                        candidat, fabricants, anciennes, reference_clean, description_with_article,
                        type_clean, n_modeles, max_length, equivs)
                rendu = rendus[candidat]
                premier = premier or (candidat, rendu)
                texte, fabricants_rendus, a_citees, e_citees = rendu
                if toutes_les_refs and len(a_citees) + len(e_citees) < nb_prevu:
                    continue
                if (fabricants_rendus or not a_des_marques) and self._tient_description(texte, max_length):
                    choisi = (candidat, rendu)
                    break
            if choisi:
                break
        # Aucun ne tient en entier : le gabarit prévu, raccourci
        template, (description_text, fabricants_str, anciennes, equivs) = choisi or premier

        final_description = self._smart_truncate_description(description_text, max_length)

        generation_info = {
            'template_used': template,
            'original_length': len(description_text),
            'final_length': len(final_description),
            'truncated': len(final_description) < len(description_text),
            'within_limit': self._tient_description(final_description, max_length),
            'largeur_px': round(largeur_px(final_description, TAILLE_DESCRIPTION_PX)),
            'fabricants_used': fabricants_str,
            'fabricants_count': len(fabricants),
            'n_modeles': n_modeles,
            'anciennes_refs': anciennes,
            'equivalentes': equivs,
            'is_supersession': '{anciennes_refs}' in template,
            'variante': variante % nb_variantes,
            'nb_variantes': nb_variantes,
        }

        self.last_generation_info['description'] = generation_info

        return {
            'description': final_description,
            'length': len(final_description),
            'info': generation_info
        }
    
    def _remplir_description(self, template: str, fabricants: List[str], anciennes: List[str],
                             reference: str, description_with_article: str, type_appareil: str,
                             n_modeles: int, max_length: int,
                             equivalentes: Optional[List[str]] = None
                             ) -> Tuple[str, str, List[str], List[str]]:
        """
        Rend un gabarit : (texte, marques retenues, anciennes réfs citées,
        équivalentes citées).
        Une seule réf liée si deux ne laissent la place à aucune marque : l'ancienne
        est gardée de préférence (décision client initiale : toujours la citer).
        """
        equivalentes = list(equivalentes or [])
        anciennes_str = self._formuler_refs_liees(anciennes, equivalentes)
        fabricants_str = self._select_fabricants_for_description(
            fabricants, template, reference, description_with_article, type_appareil, max_length,
            anciennes_refs=anciennes_str, n_modeles=n_modeles
        )
        if not fabricants_str and fabricants and len(anciennes) + len(equivalentes) > 1:
            if anciennes:
                anciennes, equivalentes = anciennes[:1], []
            else:
                equivalentes = equivalentes[:1]
            anciennes_str = self._formuler_refs_liees(anciennes, equivalentes)
            fabricants_str = self._select_fabricants_for_description(
                fabricants, template, reference, description_with_article, type_appareil,
                max_length, anciennes_refs=anciennes_str, n_modeles=n_modeles
            )
        texte = template.format(
            description=description_with_article,
            description_cap=self._adjust_first_char(description_with_article, upper=True),
            reference=reference,
            type_appareil=type_appareil,
            fabricants=fabricants_str,
            anciennes_refs=anciennes_str,
            nb_modeles=self._formuler_nb_modeles(n_modeles),
        )
        # " ".join(split()) : un {fabricants} vide ne laisse pas de double espace ;
        # ni d'espace avant une virgule (« pour congélateur , compatible »)
        return " ".join(texte.split()).replace(" ,", ","), fabricants_str, anciennes, equivalentes

    def _segment_templates_for(self, type_norm: str) -> List[str]:
        """
        Retourne les templates de segment pour un type d'appareil normalisé.
        Matching par la clé la plus LONGUE contenue dans le type (et non ==), pour
        gérer les variantes ("lave-linge top" → "lave-linge", "four micro-ondes" →
        "micro-ondes" plutôt que "four"). Retourne [] si aucun segment ne correspond.
        """
        if not type_norm:
            return []
        best_key = None
        for key in self.SEGMENT_DESCRIPTION_TEMPLATES:
            if key in type_norm and (best_key is None or len(key) > len(best_key)):
                best_key = key
        return self.SEGMENT_DESCRIPTION_TEMPLATES[best_key] if best_key else []

    def _pool_description(self, type_norm: str, n_modeles: int,
                          a_des_anciennes_refs: bool) -> Tuple[List[str], List[float]]:
        """
        Gabarits de description possibles et leur poids (L2/L3).
        Une référence qui en remplace d'autres n'utilise que les gabarits de
        supersession : ses anciennes références sont toujours citées.
        Le pool générique (25 templates) est TOUJOURS présent — garantie d'unicité
        et de diversité à grande échelle. Les templates contextuels (segment,
        forte compatibilité, supersession) ne rejoignent le pool que si leur signal
        est actif, avec un poids > 1 : favorisés sans jamais évincer le générique.
        """
        if a_des_anciennes_refs:
            pool = list(self.META_DESCRIPTION_TEMPLATES_SUPERSESSION)
            return pool, [1.0] * len(pool)

        pool = list(self.META_DESCRIPTION_TEMPLATES)
        weights = [1.0] * len(pool)

        def _boost(templates: List[str]) -> None:
            for tpl in templates:
                pool.append(tpl)
                weights.append(self.CONTEXT_TEMPLATE_WEIGHT)

        # L3 — segment d'appareil (appareil et marques en tête)
        _boost(self._segment_templates_for(type_norm))
        # L2 — forte compatibilité (la pièce équipe beaucoup de modèles)
        if n_modeles >= self.COMPAT_MODELS_THRESHOLD:
            _boost(self.META_DESCRIPTION_TEMPLATES_COMPAT)

        return pool, weights

    def _choose_description_template(self, type_norm: str, n_modeles: int,
                                     a_des_anciennes_refs: bool = False, reference: str = "",
                                     variante: int = 0) -> str:
        """Gabarit de description, fixe pour une référence (voir _ordre_deterministe)."""
        pool, weights = self._pool_description(type_norm, n_modeles, a_des_anciennes_refs)
        ordre = self._ordre_deterministe(pool, weights, reference)
        return ordre[variante % len(ordre)]

    def _select_fabricants_for_description(self, fabricants: List[str], template: str,
                                         reference: str, description_with_article: str,
                                         type_appareil: str, max_length: int,
                                         anciennes_refs: str = "", n_modeles: int = 0) -> str:
        """
        Jusqu'à MAX_MARQUES marques (« A, B et C »), autant qu'en laisse la place
        (DESCRIPTION_MAX_PX et max_length caractères, description rendue en entier).
        Retourne "" si même la première ne tient pas : une marque coupée serait pire.
        """
        marques = self._marques_uniques(fabricants)[:self.MAX_MARQUES]
        if not marques:
            return ""

        description_cap = self._adjust_first_char(description_with_article, upper=True)
        fmt_kwargs = dict(
            description=description_with_article,
            description_cap=description_cap,
            reference=reference,
            type_appareil=type_appareil,
            fabricants="",
            anciennes_refs=anciennes_refs,
            nb_modeles=self._formuler_nb_modeles(n_modeles),
        )
        for n in range(len(marques), 0, -1):
            texte = self._joindre_marques_description(marques[:n])
            fmt_kwargs['fabricants'] = texte
            rendu = " ".join(template.format(**fmt_kwargs).split())
            if self._tient_description(rendu, max_length):
                return texte
        return ""

    @staticmethod
    def _formuler_nb_modeles(n_modeles: int) -> str:
        """
        Nombre de modèles arrondi vers le bas, STRICTEMENT inférieur au vrai nombre
        pour que « plus de X modèles » reste vrai (20 → « 10 », 1 236 → « 1 200 »).
        Pas de 10 sous 100, de 50 sous 1 000, de 100 sous 10 000, de 1 000 au-delà.
        Milliers séparés par une espace (« 12 000 »).
        """
        if n_modeles <= 10:
            return str(max(n_modeles - 1, 0))
        pas = 10 if n_modeles < 100 else 50 if n_modeles < 1000 else 100 if n_modeles < 10000 else 1000
        arrondi = (n_modeles - 1) // pas * pas
        return f"{arrondi:,}".replace(",", " ")

    @classmethod
    def _formuler_refs_liees(cls, anciennes: List[str], equivalentes: List[str]) -> str:
        """Texte du champ {anciennes_refs} : anciennes puis équivalentes, séparées
        par une virgule (« ancienne réf. X, réf. équivalente Z »)."""
        return ", ".join(p for p in (cls._formuler_anciennes_refs(anciennes),
                                     cls._formuler_equivalentes(equivalentes)) if p)

    @staticmethod
    def _formuler_equivalentes(equivalentes: List[str]) -> str:
        """« réf. équivalente X », « réf. équivalentes X et Y » ; "" s'il n'y en a pas."""
        if not equivalentes:
            return ""
        if len(equivalentes) == 1:
            return f"réf. équivalente {equivalentes[0]}"
        return "réf. équivalentes " + ", ".join(equivalentes[:-1]) + " et " + equivalentes[-1]

    @staticmethod
    def _formuler_anciennes_refs(anciennes: List[str]) -> str:
        """« ancienne réf. X », « anciennes réf. X et Y » ; "" s'il n'y en a pas."""
        if not anciennes:
            return ""
        if len(anciennes) == 1:
            return f"ancienne réf. {anciennes[0]}"
        return "anciennes réf. " + ", ".join(anciennes[:-1]) + " et " + anciennes[-1]

    @staticmethod
    def _joindre_marques_description(marques: List[str]) -> str:
        """« Candy », « Candy et Hoover », « Candy, Hoover et Otsein »."""
        if len(marques) <= 1:
            return "".join(marques)
        return ", ".join(marques[:-1]) + " et " + marques[-1]

    def _smart_truncate_description(self, description: str, max_length: int) -> str:
        """
        Retire des mots entiers à la fin jusqu'à tenir (pixels et caractères), sans
        ellipse ni ponctuation pendante (« … pour lave-linge — »).
        """
        while not self._tient_description(description, max_length) and " " in description:
            description = description.rsplit(" ", 1)[0].rstrip(" —–-,:;")
        return description

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