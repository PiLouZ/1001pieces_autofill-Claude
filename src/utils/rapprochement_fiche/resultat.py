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
    'a_valider': "autre marque du groupe ou nom commercial seul",
    'absent': "aucun candidat, ni exact ni normalisé : création",
}
# Lien pièce → appareil, indépendamment du niveau
LIENS = {
    'deja_lie': "lien déjà présent sur la pièce",
    'deja_couvert': "appareil déjà lié à une autre référence de la lignée",
    'nouveau': "lien à créer",
    '': "à décider (appareil non retenu)",
}
# Motif d'une ligne qui demande un avis (moteur de questions, refonte étape 2)
MOTIFS = {
    'meme_ref_groupe': "même réf. sous une autre marque du groupe",
    'nom_meme_ref': "retrouvé par le nom commercial, même réf. (autre marque du groupe)",
    'nom_ref_differente': "même nom commercial, réf. différente",
    'nom_plusieurs': "plusieurs appareils de même nom commercial, aucun de même réf.",
    'marque_a_choisir': "marque à choisir parmi les marques annoncées",
    'exact_multiple': "plusieurs appareils de même réf.",
    'normalise_ambigu': "plusieurs écritures en base",
    'doublon_nom': "nom commercial d'un appareil déjà cité par la fiche",
}
CATEGORIES_DOUTES = {
    # Identité (§ 5.1)
    'code_produit_absent': "pièce prise dans la référence interne (pas de code produit)",
    'ref_interne_differente': "référence interne sans rapport avec le code produit",
    'ean_invalide': "clé de contrôle EAN-13 fausse",
    'ean_different': "EAN du site différent de celui de l'outil",
    'ref_interne_autre_piece': "référence interne déjà rattachée à une autre pièce",
    'libelle_different': "titre de la fiche différent du libellé de la pièce",
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
    # Mémoires de l'outil (rapprocher(..., memoires=True), étape 3)
    ean_outil: str = ''
    statut_ean_outil: str = ''          # 'a_remplir', 'identique', 'different', ''
    piece_du_produit: str = ''          # pièce qui porte déjà cette réf. interne
    ref_interne_precedente: str = ''    # même id_product, autre réf. interne (changée sur le site)
    libelle: str = ''                   # titre de la fiche, nettoyé
    libelle_outil: str = ''
    statut_libelle: str = ''            # 'a_remplir', 'identique', 'different', 'ancienne_regle', ''


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
    suspecte: str = ''                  # réf. qui ne ressemble pas à une réf. d'appareil
    # Pourquoi la ligne demande un avis (cf. MOTIFS) ; '' = rien à décider
    motif: str = ''
    # Absent : même réf. exacte sous des marques HORS du groupe (Ikea, Elica…)
    hors_groupe: List[str] = field(default_factory=list)
    type_site: str = ''                 # type donné par la fiche (table du site ou ligne)
    marque_inconnue: bool = False       # marque retenue absente de l'outil (§ 10.14)
    # Appareil connu (ou proposé) dont un champ diffère sur la fiche (type, marque,
    # écriture de la réf., nom commercial) : un écart par champ
    ecarts: List['Ecart'] = field(default_factory=list)


# Champ d'un appareil connu où l'outil et le site diffèrent → (libellé, colonne
# d'`appareils`). La marque n'est comparée que dans un même groupe de marques.
CHAMPS_ECARTS = {
    'type': ("Type", 'type'),
    'marque': ("Marque", 'manufacturer'),
    'ref': ("Réf. modèle", 'ref_modele'),
    'nom': ("Nom commercial", 'commercial_ref'),
}


@dataclass
class Ecart:
    """Champ d'un appareil connu de l'outil qui diffère sur la fiche : l'utilisateur
    garde la valeur de l'outil (par défaut) ou prend celle du site, d'un clic.
    Outil vide (nom commercial) : la valeur du site est prise sans question."""
    champ: str                          # clé de CHAMPS_ECARTS
    outil: str
    site: str
    appareil_id: int
    tranche: bool = False               # « garder l'outil » déjà choisi pour cette valeur du site

    @property
    def a_completer(self) -> bool:
        return not self.outil


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
    # Position dans la ligne « Remplace les références » de la fiche (1, 2…) :
    # mémorisée pour que la Fiche complète réécrive la ligne dans cet ordre
    rang: Optional[int] = None


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
    # Paires de réf. associées des lignes « Remplace » et « Équivalentes » (§ 5.4),
    # et les suites de réf. Whirlpool / Indesit / Beko qui n'ont pas pu être liées
    paires: List[object] = field(default_factory=list)              # PaireFiche
    suites_non_liees: List[object] = field(default_factory=list)    # SuiteNonLiee
    lignee: Dict[str, str] = field(default_factory=dict)    # ref → 'depart'/'succession'/'equivalence'
    doutes: List[Doute] = field(default_factory=list)
    liste_tronquee: bool = False        # aucun « absent » de la fiche n'est à tirer (§ 4.6)
    # Liens de provenance site présents dans l'outil mais absents de la fiche :
    # pour information (§ 6.2), vide si la liste est tronquée
    absents_de_la_fiche: List[AppareilBase] = field(default_factory=list)

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
            'absents_de_la_fiche': len(self.absents_de_la_fiche),
        }
