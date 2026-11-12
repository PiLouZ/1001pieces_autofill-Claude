"""
Résultat du rapprochement d'une fiche avec la base (CDC § 5, § 7.2)

Chaque élément porte son niveau et sa raison ; les doutes sont regroupés par
catégorie pour le résumé de l'aperçu (étape 3). Rien n'est écrit.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.utils.rapprochement_fiche.acces_base import AppareilBase

# Identification d'un appareil (§ 5.2)
NIVEAUX = {
    'exact': "marque et réf. modèle identiques, un seul candidat",
    'exact_multiple': "même réf. portée par plusieurs appareils",
    'normalise': "un seul candidat à la ponctuation près",
    'normalise_ambigu': "plusieurs écritures en base pour la même forme normalisée",
    'a_valider': "autre marque du groupe, autre type ou nom commercial seul",
    'absent': "aucun candidat, ni exact ni normalisé : création",
}
# Lien pièce → appareil, indépendamment du niveau
LIENS = {
    'deja_lie': "lien déjà présent sur la pièce",
    'deja_couvert': "appareil déjà lié à une autre référence de la lignée",
    'nouveau': "lien à créer",
    '': "à décider (appareil non retenu)",
}
CATEGORIES_DOUTES = {
    # Identité (§ 5.1)
    'code_produit_absent': "pièce prise dans la référence interne (pas de code produit)",
    'ref_interne_differente': "référence interne sans rapport avec le code produit",
    'ean_invalide': "clé de contrôle EAN-13 fausse",
    # Appareils (§ 5.2, 5.6)
    'exact_multiple': "plusieurs appareils pour la même réf., type sans départage",
    'normalise_ambigu': "plusieurs écritures en base (doublon possible)",
    'a_valider': "appareil trouvé ailleurs (marque du groupe, nom commercial, autre type)",
    'marque_a_choisir': "marque à choisir parmi les marques annoncées",
    'type_ambigu': "la base connaît l'appareil sous plusieurs types",
    'type_manquant': "type d'appareil introuvable",
    # Relations (§ 5.3, 5.4, 5.5)
    'remplacement_conflit': "l'ancienne référence a déjà un autre successeur",
    'remplacement_cycle': "le remplacement créerait un cycle",
    'appariement': "remplacement sans référence de même forme dans le code produit",
    'origine_inconnue': "format de référence inconnu : étiquette à saisir",
    'origine_ambigue': "format mélangé : étiquette à saisir",
    'ligne_melangee': "ligne d'équivalentes aux origines différentes",
    # Lecture (étape 1)
    'lecture': "ce que le lecteur n'a pas compris",
}


@dataclass
class Doute:
    categorie: str              # clé de CATEGORIES_DOUTES
    message: str
    element: str = ''           # 'appareil:12', 'remplacement:C00535957'…


@dataclass
class Identite:
    ref_piece: Optional[str] = None
    source: str = ''                    # 'code_produit', 'ref_interne', ''
    statut: str = ''                    # 'reelle', 'fantome' (deviendra réelle), 'absente'
    obsolete: bool = False
    piece_id: Optional[int] = None
    ref_interne: str = ''
    statut_ref_interne: str = ''        # 'egale', 'prefixe', 'lignee', 'differente', ''
    prefixe: str = ''
    id_product: Optional[int] = None
    ean: str = ''
    statut_ean: str = ''                # 'valide', 'cle_fausse', ''


@dataclass
class AppareilRapproche:
    numero: int                         # n° de ligne de la fiche (0 = table du site seule)
    marque_fiche: str                   # marque lue ('' = à déduire)
    ref_modele: str
    nom: str
    provenance: str                     # 'description', 'table', 'les_deux'
    niveau: str = 'absent'
    marque: str = ''                    # marque retenue (écriture de l'outil si connue)
    source_marque: str = ''             # 'entete', 'annonce', 'deduite', 'a_choisir', 'table'
    appareil_id: Optional[int] = None   # appareil retenu (None = à choisir ou à créer)
    proposition: Optional[int] = None   # appareil proposé quand le choix revient à l'utilisateur
    candidats: List[AppareilBase] = field(default_factory=list)
    lien: str = ''
    couvert_par: List[str] = field(default_factory=list)
    type: str = ''
    source_type: str = ''               # 'table', 'ligne', 'base', 'categorie', ''
    raison: str = ''
    doutes: List[str] = field(default_factory=list)


@dataclass
class Remplacement:
    ancienne: str
    nouvelle: str
    sens: str                           # 'remplace' (X → pièce) ou 'remplacee_par' (pièce → Y)
    statut: str = ''                    # cf. STATUTS_REMPLACEMENT
    appariement: str = ''               # 'unique', 'forme', 'a_choisir'
    successeur_actuel: Optional[str] = None
    fantome_a_creer: bool = False
    raison: str = ''


STATUTS_REMPLACEMENT = {
    'nouveau': "remplacement à créer",
    'deja_present': "déjà en base",
    'confirme_par_chaine': "la chaîne en base mène déjà à la nouvelle référence",
    'conflit': "l'ancienne référence a un autre successeur",
    'cycle': "créerait un cycle",
    'identique': "même référence des deux côtés, ignoré",
}


@dataclass
class Equivalence:
    reference: str
    source: str                         # 'code_produit', 'equivalentes', 'ref_marque'
    ligne: int                          # n° de ligne de la fiche (0 = code produit)
    origine: str = ''                   # étiquette d'origine
    source_origine: str = ''            # 'format', 'fiche', ''
    statut: str = ''                    # cf. STATUTS_EQUIVALENCE
    raison: str = ''


STATUTS_EQUIVALENCE = {
    'nouveau': "équivalence à créer",
    'deja_dans_le_groupe': "déjà dans le groupe de la pièce",
    'fusion_groupes': "déjà dans un autre groupe : les groupes fusionneront",
    'dans_la_succession': "déjà reliée à la pièce par la chaîne de remplacements",
    'ecartee': "référence écartée par l'utilisateur",
}


@dataclass
class Rapprochement:
    identite: Identite
    appareils: List[AppareilRapproche] = field(default_factory=list)
    remplacements: List[Remplacement] = field(default_factory=list)
    equivalences: List[Equivalence] = field(default_factory=list)
    lignee: Dict[str, str] = field(default_factory=dict)    # ref → 'depart'/'succession'/'equivalence'
    doutes: List[Doute] = field(default_factory=list)
    liste_tronquee: bool = False        # aucun « absent » de la fiche n'est à tirer (§ 4.6)

    def doutes_par_categorie(self) -> Dict[str, List[Doute]]:
        groupes: Dict[str, List[Doute]] = defaultdict(list)
        for d in self.doutes:
            groupes[d.categorie].append(d)
        return {c: groupes[c] for c in CATEGORIES_DOUTES if c in groupes}

    def resume(self) -> Dict[str, object]:
        """Comptes par niveau, lien, statut et catégorie de doute."""
        annonces = [a for a in self.appareils if a.marque_fiche == '' and a.provenance != 'table']
        return {
            'ref_piece': self.identite.ref_piece,
            'statut_piece': self.identite.statut,
            'appareils': len(self.appareils),
            'niveaux': dict(Counter(a.niveau for a in self.appareils)),
            'liens': dict(Counter(a.lien for a in self.appareils)),
            'provenances': dict(Counter(a.provenance for a in self.appareils)),
            'marques_deduites': sum(1 for a in annonces if a.source_marque == 'deduite'),
            'marques_a_deduire': len(annonces),
            'remplacements': dict(Counter(r.statut for r in self.remplacements)),
            'equivalences': dict(Counter(e.statut for e in self.equivalences)),
            'doutes': {c: len(v) for c, v in self.doutes_par_categorie().items()},
        }
