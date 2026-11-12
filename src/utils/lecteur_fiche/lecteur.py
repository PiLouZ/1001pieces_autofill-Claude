"""
Lecteur de description de fiche produit (CDC import fiches site, § 4)

Transforme une description (HTML du site ou du back-office, ou texte collé)
en données structurées, SANS rien écrire et sans Qt :
- lecture guidée par tous les profils « Fiche » (score, meilleur profil, § 4.2),
  et repérage par texte en secours (anciens libellés compris) ;
- code produit, remplacements, lignes d'équivalentes (séparées, numérotées),
  références par marque (« Réf. fabricant »), marques (faisceau d'indices,
  § 4.4), lignes d'appareils (RÉF - NOM, anciens formats BSH « RÉF/01 NOM »,
  PNC Electrolux / 12NC Whirlpool seuls ou suivis du nom, § 4.5), liste
  réduite (§ 4.6) ;
- ce qui n'a pas été compris (non_compris) alimente les doutes des étapes
  suivantes (rapprochement, aperçu). Le texte libre de l'en-tête
  (caractéristiques, dimensions, tableaux) est gardé à part (textes_libres) :
  il n'est signalé que s'il semble parler de références.

Les libellés et formats ci-dessous ont été mesurés sur les 13 302 descriptions
du site (2026-11-12) ; toute nouvelle variante s'ajoute ici.
"""

import re
import unicodedata
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from src.utils.lecteur_fiche.modeles import ModeleLecture, Repere, cle_texte
from src.utils.lecteur_fiche.normalisation import Bloc, longueur_visible, normaliser

# --- Repérage par texte (secours) ---------------------------------------------
_REF = r"r[ée]f[ée]rences?"
LIBELLES_EQUIVALENTES = (
    re.compile(rf"^{_REF}\s+[ée]quivalentes?\s*:?\s*(.*)$", re.I),
)
LIBELLES_REMPLACE = (
    re.compile(rf"^remplacen?t?\s+(?:les\s+|la\s+)?(?:anciennes?\s+)?{_REF}\s*:?\s*(.*)$", re.I),
    # « Remplace les dimensions : C00280008 … » : faute de saisie du site (fiche 7188)
    re.compile(r"^remplacen?t?\s+les\s+dimensions\s*:\s*(.*\d.*)$", re.I),
    re.compile(r"^remplacen?t?\s+(?:les\s+)?(?:produits|pi[eè]ces|articles)(?:\s+suivante?s)?\s*:\s*(.*)$",
               re.I),
    re.compile(r"^remplacen?t?\s*:\s*(.*)$", re.I),
)
# Relation inverse : cette pièce est remplacée par une autre (successeur)
LIBELLES_REMPLACEE_PAR = (
    re.compile(rf"^remplac[ée]e?\s+par\s*(?:la\s+|les\s+)?(?:{_REF}\s*)?:?\s*(.*)$", re.I),
)
LIBELLES_CODE_PRODUIT = (
    re.compile(r"^code\s+produit\s*:?\s*(.*)$", re.I),
)
# Annonce des marques : « Compatible avec … » (actuel), « Montage sur … » (ancien)
LIBELLES_ANNONCE_MARQUES = (
    re.compile(r"^compatibles?\s+(?:avec\b)?\s*:?\s*(.*)$", re.I),
    re.compile(r"^montage\s+sur\s*:?\s*(.*)$", re.I),
)
TOUTES_MARQUES = re.compile(r"^(?:compatible|montage\s+sur)\s+(?:avec\s+)?toutes\s+(?:les\s+)?marques",
                            re.I)
# Titres de liste (comparés sous forme cle_texte : minuscules, sans « : » final)
_NON_EXHAUSTIVE = r"\(?\s*liste\s+non[\s-]exhaustive\s*!?\s*\)?"
_FIN_TITRE = rf"(?:\s*:?\s*{_NON_EXHAUSTIVE})?$"
TITRES_LISTE = (
    # « Appareils compatibles », « Appareil(s) compatible », « Appareils comaptibles »…
    re.compile(r"^(?:liste\s+des\s+)?appareils?(?:\(s\))?\s+co(?:mp|map|mt?p)?a?t?ibles?"
               r"(?:\s+avec\s+cette\s+pi[eè]ce)?" + _FIN_TITRE),
    # « Appareils employant cette pièce / ce thermostat / ces sacs », « utilisant ce filtre »
    re.compile(r"^appareils?(?:\(s\))?\s+(?:employants?|utilisants?)\s+(?:cette|cet|ce|ces)"
               r"(?:\s+\S+){1,3}" + _FIN_TITRE),
    re.compile(r"^mod[eè]les\s+compatibles" + _FIN_TITRE),
    # Listes de références commerciales des appareils
    re.compile(r"^r[ée]f[ée]rences\s+(?:commerciales\s+)?(?:compatibles|employant\s+cette\s+pi[eè]ce)"
               + _FIN_TITRE),
    # Anciens titres : suivis soit d'appareils, soit de lignes « Réf. fabricant »
    re.compile(r"^r[ée]f[ée]rence\(?s?\)?\s+de\s+l['’]article\s+(?:par\s+marque|pour\s+mod[eè]les)$"),
)
SOUS_TITRE_NON_EXHAUSTIVE = re.compile(rf"^{_NON_EXHAUSTIVE}$")
_TITRE_NON_EXHAUSTIF = re.compile(r"non[\s-]exhaustive")
# « Référence EGO : 55.13059.010 » : références de la pièce chez un fabricant
REF_MARQUE = re.compile(r"^r[ée]f[ée]rences?\s+(?P<marque>[^\s:][^:]{0,25}?)\s*:\s*(?P<refs>\S.*)$",
                        re.I)
MESSAGE_TROP_VOLUMINEUX = "données trop volumineuses pour l'affichage"
# « Bosch Réf. fabricant : 00123456 » ou « Réf. fabricant : … » sous une marque
REF_FABRICANT = re.compile(
    r"^(?:(?P<marque>.+?)\s+)?r[ée]f(?:[ée]rence)?\.?\s*(?:du\s+)?fabricant\s*:\s*(?P<refs>.*)$", re.I)
# Texte de l'en-tête qui semble parler de références : signalé s'il n'est pas lu
_EN_TETE_SUSPECT = re.compile(
    r"r[ée]f[ée]rence|\br[ée]f\b|code|remplac|[ée]quivalen|compatib|appareils?\b|mod[eè]les?\b", re.I)
# Blocs collés depuis un navigateur (extension), sans rapport avec la fiche
IDS_IGNORES = frozenset({'sconnect-is-installed'})
BALISES_TABLEAU = frozenset({'td', 'th', 'tr', 'table', 'tbody', 'thead'})

# --- Lignes d'appareils (§ 4.5) -----------------------------------------------
_SEP_REF_NOM = ' - '
_BSH = re.compile(r"^(\S*[A-Za-z0-9]\S*/\d{1,2})\s+(\S.*)$")        # RÉF/01 NOM
_PNC_SERIE = re.compile(r"^\d{8,13}(?:\s+\d{8,13})+$")               # PNC alignés
_PNC_NOM = re.compile(r"^(\d{8,13})\s+(\S.*)$")                      # PNC / 12NC NOM
_CHIFFRE = re.compile(r"\d")
# « VF3017 (VF 3017) » : réf. puis son écriture d'origine entre parenthèses
_REF_PARENTHESES = re.compile(r"^(\S*\d\S*)\s+\(([^()]+)\)$")
# Cotes du bloc Dimensions (« A : 92 cm », « C : - cm ») : pas des appareils
_COTE = re.compile(r"^[A-Za-zØø]{1,3}\s*:\s*[-–\d.,\s]*\s*(?:cm|mm|m|w|v|kw)?\s*$", re.I)
# Marque d'une ligne d'équivalentes : « Rosières : 49025106 … » (fiche 7188)
_MARQUE_EN_TETE = re.compile(r"^(?P<marque>[^\d:]{2,30}?)\s*:\s*(?P<refs>.*\d.*)$")
# Suite d'une ligne « Réf. fabricant » : « POUR APPAREILS VN606E / VF6017E »
_POUR_APPAREILS = re.compile(r"^pour\s+(?:les\s+)?(?:appareils?|mod[eè]les?)\s*:?\s*(?P<refs>.*)$", re.I)
_SEP_REFS = re.compile(r"[\s,;]+")
_SEP_MARQUES = re.compile(r"\s*(?:,|;|/|\s\+\s|\set\s)\s*", re.I)

# Marque reconnue sans être annoncée ni connue : texte court, sans chiffre
_LONGUEUR_MAX_MARQUE = 40
_MOTS_MAX_MARQUE = 4
# Part de la limite au-delà de laquelle une liste est probablement réduite
_SEUIL_LIMITE = 0.97


# =============================================================================
# Résultat
# =============================================================================

@dataclass
class LigneAppareil:
    numero: int                 # n° de ligne d'appareil dans la liste (1…)
    marque: Optional[str]       # marque de la section (None = inconnue)
    ref_modele: str
    nom: str                    # nom commercial, lu tel quel ('' si absent)
    format: str                 # 'ref_nom', 'bsh', 'pnc', 'pnc_nom', 'ref_seule'
    bloc: int                   # index du bloc normalisé
    # 'entete' (section), 'annonce' (seule marque annoncée), 'annonces' (marque à
    # choisir parmi les marques annoncées, au rapprochement), '' (aucune)
    source_marque: str = ''
    type_ligne: str = ''        # type écrit sur la ligne ou sa suite (« Four Vapeur »)


@dataclass
class LigneEquivalentes:
    numero: int                 # n° de la ligne dans la fiche (1…)
    references: List[str]
    bloc: int
    source: str                 # 'profil' ou 'texte'
    origine: str = ''           # marque donnée par la fiche (références par marque)


@dataclass
class NonCompris:
    nature: str                 # cf. NATURES_NON_COMPRIS
    texte: str
    bloc: Optional[int] = None
    detail: str = ''


NATURES_NON_COMPRIS = {
    'bloc_non_lu': "bloc de l'en-tête qui semble parler de références, non lu",
    'ligne_non_lue': "ligne de la liste non reconnue",
    'marque_inconnue': "marque ni annoncée ni connue",
    'appareil_sans_marque': "appareil sans marque, aucune marque annoncée",
    'marque_a_deduire': "appareil sans en-tête de marque, plusieurs marques annoncées",
    'marque_sans_appareil': "marque sans appareil",
    'marque_annoncee_absente': "marque annoncée absente de la liste",
    'liste_sans_titre': "liste d'appareils sans titre reconnu",
    'profil_ambigu': "plusieurs profils Fiche lisent aussi bien la fiche",
    'lecture_divergente': "les meilleurs profils ne lisent pas la même chose",
    'code_produit_absent': "pas de ligne « Code produit »",
    'code_produit_multiple': "plusieurs lignes « Code produit »",
    'liste_tronquee': "liste d'appareils probablement réduite",
}


@dataclass
class ScoreProfil:
    nom: str
    score: int                  # nombre de blocs reconnus par le profil (§ 4.2)
    departage: int              # concordances secondaires (sous-titre, Informations, titre)
    blocs: List[str]            # blocs reconnus : 'code_produit', 'remplace'…


@dataclass
class LectureFiche:
    titre: str = ''
    marques_annoncees: List[str] = field(default_factory=list)
    source_annonce: str = ''                # 'description' ou 'produit' (marque du produit)
    toutes_marques: bool = False            # « Compatible toutes marques »
    code_produit: List[str] = field(default_factory=list)
    remplace: List[str] = field(default_factory=list)
    remplacee_par: List[str] = field(default_factory=list)   # successeur(s) annoncé(s)
    equivalentes: List[LigneEquivalentes] = field(default_factory=list)
    references_par_marque: List[LigneEquivalentes] = field(default_factory=list)
    titre_liste: str = ''
    liste_non_exhaustive: bool = False
    marques: List[str] = field(default_factory=list)     # sections, dans l'ordre
    appareils: List[LigneAppareil] = field(default_factory=list)
    informations: List[str] = field(default_factory=list)   # bloc Informations (alert)
    textes_libres: List[str] = field(default_factory=list)  # autre texte, non relationnel
    liste_tronquee: bool = False
    motifs_troncature: List[str] = field(default_factory=list)
    profil: Optional[str] = None            # profil retenu (None = repérage par texte)
    profils_equivalents: List[str] = field(default_factory=list)  # même lecture, même score
    scores: List[ScoreProfil] = field(default_factory=list)
    profil_ambigu: bool = False
    sources: Dict[str, str] = field(default_factory=dict)  # bloc → 'profil' / 'texte'
    libelles: Dict[str, str] = field(default_factory=dict)  # bloc → libellé lu (« Code produit : »)
    blocs_reperes: Dict[str, int] = field(default_factory=dict)  # bloc → index du 1er bloc
    non_compris: List[NonCompris] = field(default_factory=list)
    longueur_visible: int = 0

    @property
    def reference_principale(self) -> Optional[str]:
        """1ʳᵉ réf. du code produit (= la pièce, § 5.1)."""
        return self.code_produit[0] if self.code_produit else None

    @property
    def nb_lignes(self) -> int:
        return len(self.appareils)

    @property
    def lue_par_texte(self) -> bool:
        """Au moins un bloc n'a été reconnu que par le repérage par texte."""
        return 'texte' in self.sources.values()

    def resume(self) -> Dict[str, object]:
        """Résumé compact (mesures, journaux)."""
        return {
            'profil': self.profil, 'profil_ambigu': self.profil_ambigu,
            'code_produit': self.code_produit, 'remplace': len(self.remplace),
            'equivalentes': [e.references for e in self.equivalentes],
            'marques': len(self.marques), 'lignes': self.nb_lignes,
            'tronquee': self.liste_tronquee, 'sources': dict(self.sources),
            'non_compris': len(self.non_compris),
        }


# =============================================================================
# Lecture
# =============================================================================

@lru_cache(maxsize=100_000)
def cle_marque(nom: str) -> str:
    """Forme de comparaison d'une marque : sans accents ni casse (« Scholtès » = « Scholtes »)."""
    decompose = unicodedata.normalize('NFKD', nom or '')
    return ''.join(c for c in decompose if not unicodedata.combining(c)).casefold().strip()


def decouper_references(valeur: str, separateur: str = ' ') -> List[str]:
    """« A B, C » → ['A', 'B', 'C'] (séparateur du profil, espaces, virgules, ;)."""
    if separateur and separateur.strip():
        valeur = valeur.replace(separateur, ' ')
    return [r for r in _SEP_REFS.split(valeur or '') if r]


def decouper_marques(texte: str, marques_connues: Set[str]) -> Tuple[List[str], List[str]]:
    """
    Marques d'une annonce sans liens (« Bosch Siemens, De Dietrich et Sauter »).
    Rend (marques, sûres) : les marques connues sont reconnues sur plusieurs mots
    (« De Dietrich ») ; sans marques connues, chaque mot est une marque, non sûre.
    """
    marques, sures = [], []
    for morceau in _SEP_MARQUES.split(texte or ''):
        mots = morceau.split()
        i = 0
        while i < len(mots):
            trouve = 0
            for j in range(min(len(mots), i + _MOTS_MAX_MARQUE), i, -1):
                if cle_marque(' '.join(mots[i:j])) in marques_connues:
                    trouve = j
                    break
            if trouve:
                nom = ' '.join(mots[i:trouve])
                marques.append(nom)
                sures.append(nom)
                i = trouve
            else:
                marques.append(mots[i])
                i += 1
    return marques, sures


def _premier(motifs: Sequence[re.Pattern], texte: str) -> Optional[str]:
    for motif in motifs:
        m = motif.match(texte)
        if m:
            return m.group(1).strip()
    return None


class _Lecture:
    """Une lecture de la fiche avec un modèle (ou aucun : texte seul)."""

    def __init__(self, blocs: List[Bloc], modele: Optional[ModeleLecture],
                 marques_connues: Set[str], types_connus: Set[str], marque_produit: str = ''):
        self.marque_produit = marque_produit
        self.blocs = blocs
        self.modele = modele
        self.marques_connues = marques_connues
        self.types_connus = types_connus
        self.r = LectureFiche()
        self.reconnus_profil: List[str] = []
        self.departage = 0
        self.annoncees: Set[str] = set()
        self.annoncees_sures: List[str] = []

    # --- Lignes de références -------------------------------------------------
    def _valeur(self, bloc: Bloc, repere: Optional[Repere],
                motifs: Sequence[re.Pattern]) -> Tuple[Optional[str], str]:
        if repere is not None:
            v = repere.valeur(bloc)
            if v is not None:
                return v, 'profil'
        v = _premier(motifs, bloc.texte)
        return (v, 'texte') if v is not None else (None, '')

    def _noter(self, nom: str, source: str, bloc: Bloc, libelle: str):
        self.r.libelles.setdefault(nom, libelle)
        self.r.blocs_reperes.setdefault(nom, bloc.index)
        if source == 'profil':
            self.reconnus_profil.append(nom)
        # Une seule source par bloc : 'texte' l'emporte (variante à signaler)
        if self.r.sources.get(nom) != 'texte':
            self.r.sources[nom] = source

    @staticmethod
    def _libelle(bloc: Bloc, valeur: str) -> str:
        texte = bloc.texte
        return texte[:len(texte) - len(valeur)].strip() if valeur and texte.endswith(valeur) \
            else texte

    def _ligne_references(self, bloc: Bloc) -> bool:
        m = self.modele
        sep = m.separateur_references if m else ' '
        # Équivalentes et remplace avant le code produit (libellés plus précis)
        v, src = self._valeur(bloc, m.equivalentes if m else None, LIBELLES_EQUIVALENTES)
        if v is not None:
            origine = ''
            marque = _MARQUE_EN_TETE.match(v)
            if marque:                      # « Références équivalentes Rosières : … »
                origine, v = marque.group('marque').strip(), marque.group('refs')
            refs = decouper_references(v, sep)
            self.r.equivalentes.append(LigneEquivalentes(
                len(self.r.equivalentes) + 1, refs, bloc.index, src, origine))
            self._noter('equivalentes', src, bloc, self._libelle(bloc, v))
            return True
        v = _premier(LIBELLES_REMPLACEE_PAR, bloc.texte)
        if v is not None:
            self.r.remplacee_par.extend(r for r in decouper_references(v, sep)
                                        if r not in self.r.remplacee_par)
            self._noter('remplacee_par', 'texte', bloc, self._libelle(bloc, v))
            return True
        v, src = self._valeur(bloc, m.remplace if m else None, LIBELLES_REMPLACE)
        if v is not None:
            self.r.remplace.extend(r for r in decouper_references(v, sep)
                                   if r not in self.r.remplace)
            self._noter('remplace', src, bloc, self._libelle(bloc, v))
            return True
        v, src = self._valeur(bloc, m.code_produit if m else None, LIBELLES_CODE_PRODUIT)
        if v is not None:
            if self.r.code_produit:
                self.r.non_compris.append(NonCompris('code_produit_multiple', bloc.texte,
                                                     bloc.index))
            else:
                self.r.code_produit = decouper_references(v, sep)
            self._noter('code_produit', src, bloc, self._libelle(bloc, v))
            return True
        return False

    def _ref_fabricant(self, bloc: Bloc, marque: Optional[str]) -> bool:
        """
        « MARQUE Réf. fabricant : RÉF », ou « Référence EGO : RÉF » (marque connue ou
        écrite en capitales) : références de la pièce par marque.
        """
        m = REF_FABRICANT.match(bloc.texte)
        nom_marque = ''
        if not m:
            m = REF_MARQUE.match(bloc.texte)
            nom = m.group('marque') if m else ''
            if not m:
                return False
            nom_marque = self._marque_proche(nom)
            refs_tete = decouper_references(m.group('refs'))
            # « Référence Ego : 20.41222.000 » : un nom propre suivi de références
            fabricant = (len(nom.split()) <= 2 and nom[:1].isupper() and refs_tete
                         and all(_CHIFFRE.search(x) for x in refs_tete))
            if not (nom.isupper() or nom_marque or fabricant):
                return False
        texte_refs = m.group('refs')
        refs = decouper_references(texte_refs)
        # Références de tête seulement (avec un chiffre) ; la suite « POUR APPAREILS
        # VN606E / VF6017E » donne des appareils, sinon elle est signalée non lue
        fin = next((k for k, r in enumerate(refs) if not any(c.isdigit() for c in r)), len(refs))
        origine = (nom_marque or m.group('marque') or marque or '').strip()
        if fin < len(refs):
            suite = ' '.join(refs[fin:])
            pour = _POUR_APPAREILS.match(suite)
            appareils = [x for x in re.split(r"[\s,;/]+", pour.group('refs')) if _CHIFFRE.search(x)] \
                if pour else []
            if appareils:
                marque_app = marque or origine or None
                for ref in appareils:
                    self.r.appareils.append(LigneAppareil(
                        len(self.r.appareils) + 1, marque_app, ref, '', 'ref_seule', bloc.index,
                        'entete' if marque_app else ''))
            else:
                self.r.non_compris.append(NonCompris('bloc_non_lu', bloc.texte, bloc.index, suite))
            refs = refs[:fin]
        if refs:
            self.r.references_par_marque.append(LigneEquivalentes(
                len(self.r.references_par_marque) + 1, refs, bloc.index, 'texte', origine))
            self._noter('references_par_marque', 'texte', bloc, bloc.texte[:m.start('refs')].strip())
        return True

    def _marque_proche(self, nom: str) -> str:
        """Marque connue écrite telle quelle ou à une faute près (« Brauknecht »
        → « Bauknecht », fiche 7091) ; '' sinon."""
        cle = cle_marque(nom)
        if not cle:
            return ''
        if cle in self.marques_connues or cle in self.annoncees:
            return nom
        import difflib
        proches = difflib.get_close_matches(cle, list(self.annoncees) or list(self.marques_connues),
                                            n=1, cutoff=0.88)
        if proches and len(cle) >= 6:
            ecrite = next((n for n in self.r.marques_annoncees if cle_marque(n) == proches[0]), '')
            return ecrite or proches[0].capitalize()
        return ''

    def _titre_liste(self, bloc: Bloc) -> Optional[str]:
        m = self.modele
        cle = cle_texte(bloc.texte)
        if m and m.titres_liste and cle == m.titres_liste[0]:
            return 'profil'
        if any(t.match(cle) for t in TITRES_LISTE):
            return 'texte'
        return None

    # --- Marques ----------------------------------------------------------------
    def _annonce(self, bloc: Bloc) -> bool:
        """Ligne « Compatible avec » / « Montage sur » : marques annoncées."""
        texte = bloc.texte
        if TOUTES_MARQUES.match(texte):
            self.r.toutes_marques = True
            return True
        valeur = _premier(LIBELLES_ANNONCE_MARQUES, texte)
        if valeur is None:
            return False
        if self.r.marques_annoncees:
            return True                       # 1re annonce seule retenue
        if bloc.liens:
            noms = [n for n in bloc.liens if n]
            sures = list(noms)
        else:
            noms, sures = decouper_marques(valeur, self.marques_connues)
        self._annoncer(noms, sures, 'description')
        return True

    def _annoncer(self, noms: List[str], sures: List[str], source: str):
        self.r.marques_annoncees = noms
        self.r.source_annonce = source
        self.annoncees = {cle_marque(n) for n in noms}
        self.annoncees_sures = sures

    def _connue(self, texte: str) -> bool:
        cle = cle_marque(texte)
        return cle in self.annoncees or cle in self.marques_connues

    def _est_marque(self, bloc: Bloc) -> Optional[bool]:
        """None = pas une marque ; True = marque reconnue ; False = marque inconnue."""
        texte = bloc.texte
        if _SEP_REF_NOM in texte or ':' in texte:
            return None
        if self._connue(texte):
            return True
        m = self.modele
        indice_balise = bool(m and m.entete_marque and m.entete_marque.balise != 'div'
                             and bloc.balise == m.entete_marque.balise)
        if bloc.id or indice_balise:
            return False
        if not _CHIFFRE.search(texte) and len(texte) <= _LONGUEUR_MAX_MARQUE:
            return False
        return None

    # --- Appareils ---------------------------------------------------------------
    def _type_en_fin(self, nom: str) -> Tuple[str, str]:
        """« KOXS6630 Four Vapeur » → (« KOXS6630 », « Four Vapeur ») si type connu."""
        if not self.types_connus or not nom:
            return nom, ''
        mots = nom.split()
        for k in range(min(4, len(mots) - 1), 0, -1):
            fin = ' '.join(mots[-k:])
            if cle_marque(fin) in self.types_connus:
                return ' '.join(mots[:-k]), fin
        # « AKZM769/WH Four à Pyrolyse » : le type connu ouvre la fin du nom
        for i in range(1, len(mots)):
            t = self._type_en_tete(' '.join(mots[i:]))
            if t:
                return ' '.join(mots[:i]), t
        return nom, ''

    def _type_en_tete(self, texte: str) -> str:
        """« Four à Pyrolyse » → « Four » : le plus long début qui est un type connu
        (texte sans chiffre seulement)."""
        if not self.types_connus or _CHIFFRE.search(texte or ''):
            return ''
        mots = texte.split()
        for k in range(min(4, len(mots)), 0, -1):
            debut = ' '.join(mots[:k])
            if cle_marque(debut) in self.types_connus:
                return debut
        return ''

    @staticmethod
    def _appareils(texte: str) -> List[Tuple[str, str, str]]:
        if _SEP_REF_NOM in texte:
            ref, _, nom = texte.partition(_SEP_REF_NOM)
            ref, nom = ref.strip(), nom.strip()
            # Philips « HR 6325 - HR632501 » : à gauche la famille, à droite le modèle
            # qui la prolonge (fiche 7138) ; la réf. est celle de droite
            if ' ' in ref and nom and ' ' not in nom and len(nom) > len(ref.replace(' ', '')) \
                    and nom.upper().startswith(ref.replace(' ', '').upper()):
                return [(nom, ref, 'famille_modele')]
            return [(ref, nom, 'ref_nom')] if ref else []
        m = _REF_PARENTHESES.match(texte)
        if m:
            return [(m.group(1), m.group(2).strip(), 'ref_parentheses')]
        if _PNC_SERIE.match(texte):
            return [(pnc, '', 'pnc') for pnc in texte.split()]
        m = _BSH.match(texte)
        if m:
            return [(m.group(1), m.group(2).strip(), 'bsh')]
        m = _PNC_NOM.match(texte)
        if m:
            return [(m.group(1), m.group(2).strip(), 'pnc_nom')]
        if _CHIFFRE.search(texte):
            return [(texte, '', 'ref_seule')]
        return []

    def _ajouter_appareils(self, bloc: Bloc, marque: Optional[str], source_marque: str,
                           type_section: str) -> bool:
        lignes = self._appareils(bloc.texte)
        for ref, nom, fmt in lignes:
            nom, type_ligne = self._type_en_fin(nom) if fmt != 'ref_nom' else (nom, '')
            self.r.appareils.append(LigneAppareil(
                len(self.r.appareils) + 1, marque, ref, nom, fmt, bloc.index,
                source_marque, type_ligne or type_section))
        if lignes and marque is None:
            # Plusieurs marques annoncées : à déduire au rapprochement (étape 2)
            nature = 'marque_a_deduire' if len(self.r.marques_annoncees) > 1 \
                else 'appareil_sans_marque'
            self.r.non_compris.append(NonCompris(nature, bloc.texte, bloc.index))
        return bool(lignes)

    # --- Déroulé -------------------------------------------------------------------
    def _en_tete(self, bloc: Bloc):
        """Bloc de l'en-tête hors repères : titre, texte libre, ou non lu s'il parle de réf."""
        r = self.r
        if not r.titre and (bloc.balise in ('h1', 'h2', 'h3') or 'class_perso1' in bloc.classes):
            r.titre = bloc.texte
        elif bloc.balise in BALISES_TABLEAU or not _EN_TETE_SUSPECT.search(bloc.texte):
            r.textes_libres.append(bloc.texte)
        else:
            r.non_compris.append(NonCompris('bloc_non_lu', bloc.texte, bloc.index))

    def lire(self) -> LectureFiche:
        r = self.r
        blocs = [b for b in self.blocs if b.id not in IDS_IGNORES]
        # Marques annoncées d'abord : indice pour la liste
        for bloc in blocs:
            if self._annonce(bloc) and r.marques_annoncees:
                break
        # Sans annonce : marques connues du produit (« Whirlpool Laden Ignis Bauknecht »)
        if not r.marques_annoncees and not r.toutes_marques and self.marque_produit:
            _, sures = decouper_marques(self.marque_produit, self.marques_connues)
            if sures:
                self._annoncer(sures, [], 'produit')
        marque_annoncee = r.marques_annoncees[0] if len(r.marques_annoncees) == 1 else None

        dans_liste = False
        marque: Optional[str] = None
        type_section = ''
        precedent_appareil = False
        nb_par_marque: Dict[str, int] = {}
        marques_refs: Set[str] = set()
        classes_liste = self.modele.classes_liste if self.modele else frozenset()
        for bloc in blocs:
            texte = bloc.texte
            apres_appareil, precedent_appareil = precedent_appareil, False
            if self._annonce(bloc) or self._ligne_references(bloc):
                continue
            src = self._titre_liste(bloc)
            if src and not r.titre_liste:
                r.titre_liste = texte.rstrip(' :')
                if _TITRE_NON_EXHAUSTIF.search(cle_texte(texte)):
                    r.liste_non_exhaustive = True
                self._noter('titre_liste', src, bloc, texte)
                dans_liste = True
                continue
            cle = cle_texte(texte)
            if SOUS_TITRE_NON_EXHAUSTIVE.match(cle):
                r.liste_non_exhaustive = True
                continue
            if dans_liste and re.fullmatch(r"[.…\s]+", texte):
                r.motifs_troncature.append('points_de_suite')
                continue
            if MESSAGE_TROP_VOLUMINEUX in cle:
                r.motifs_troncature.append('message_trop_volumineux')
                continue
            if 'alert' in ' '.join(bloc.classes | bloc.classes_parents):
                r.informations.append(texte)        # bloc « Informations » du profil
                continue
            if self._ref_fabricant(bloc, marque if dans_liste else None):
                if marque:
                    marques_refs.add(marque)
                continue
            if not dans_liste:
                # Début de liste sans titre : bloc dans le conteneur de liste ou
                # en-tête de marque portant un id
                debut = ((classes_liste and classes_liste & (bloc.classes_parents | bloc.classes))
                         or 'class_perso5' in bloc.classes_parents
                         or (bloc.id and self._est_marque(bloc) is not None))
                if debut and bloc.balise not in BALISES_TABLEAU:
                    dans_liste = True
                    r.non_compris.append(NonCompris('liste_sans_titre', texte, bloc.index))
            if not dans_liste:
                self._en_tete(bloc)
                continue
            if bloc.balise in BALISES_TABLEAU or _COTE.match(texte) or (
                    ':' in texte and _SEP_REF_NOM not in texte
                    and not _CHIFFRE.search(texte.split(':')[0])):
                r.textes_libres.append(texte)       # tableau ou « Dimensions : … » après la liste
                continue
            # Type d'appareil : suite de la ligne précédente, ou en-tête de section ;
            # « Four à Pyrolyse » après un appareil : son type commence par « Four »
            if apres_appareil and not self._connue(texte) and \
                    cle_marque(texte) not in self.types_connus and self._type_en_tete(texte):
                for a in r.appareils:
                    if a.bloc == r.appareils[-1].bloc:
                        a.type_ligne = self._type_en_tete(texte)
                continue
            if cle_marque(texte) in self.types_connus and not self._connue(texte):
                if apres_appareil:
                    for a in r.appareils:
                        if a.bloc == r.appareils[-1].bloc:
                            a.type_ligne = texte
                else:
                    type_section = texte
                continue
            # Marque, puis ligne d'appareil
            statut = self._est_marque(bloc)
            if statut is not None:
                marque = texte
                if marque not in nb_par_marque:
                    r.marques.append(marque)
                    nb_par_marque[marque] = 0
                if statut is False:
                    r.non_compris.append(NonCompris('marque_inconnue', texte, bloc.index))
                continue
            avant = len(r.appareils)
            if marque is not None:
                ok = self._ajouter_appareils(bloc, marque, 'entete', type_section)
            else:
                source = 'annonce' if marque_annoncee else \
                    ('annonces' if r.marques_annoncees else '')
                ok = self._ajouter_appareils(bloc, marque_annoncee, source, type_section)
            if ok:
                precedent_appareil = True
                if marque is not None:
                    nb_par_marque[marque] += len(r.appareils) - avant
                continue
            r.non_compris.append(NonCompris('ligne_non_lue', texte, bloc.index))

        # Marques qui ne portent que des « Réf. fabricant » : pas des sections
        for nom in marques_refs:
            if nb_par_marque.get(nom) == 0:
                del nb_par_marque[nom]
                r.marques.remove(nom)
        for nom, nb in nb_par_marque.items():
            if nb == 0:
                r.non_compris.append(NonCompris('marque_sans_appareil', nom))
        if r.marques:
            presentes = {cle_marque(m) for m in r.marques}
            for nom in self.annoncees_sures:
                if cle_marque(nom) not in presentes:
                    r.non_compris.append(NonCompris('marque_annoncee_absente', nom))
        if not r.code_produit:
            r.non_compris.append(NonCompris('code_produit_absent', ''))
        self._departage()
        return r

    def _departage(self):
        """Concordances secondaires entre la fiche et le profil (ne font pas le score)."""
        m = self.modele
        if m is None:
            return
        attend_ne = any(SOUS_TITRE_NON_EXHAUSTIVE.match(t) for t in m.titres_liste)
        if attend_ne == self.r.liste_non_exhaustive:
            self.departage += 1
        if m.inclure_informations == bool(self.r.informations):
            self.departage += 1
        # Intitulés du bloc Informations du profil : présents +1, absents -1
        if m.inclure_informations and self.r.informations:
            lus = {cle_texte(t) for t in self.r.informations}
            self.departage += sum(1 if t in lus else -1 for t in m.informations_titres)
        # Titre : textes fixes du gabarit Titre présents +, absents - (titre absent :
        # le gabarit le plus simple l'emporte)
        titre = cle_texte(self.r.titre)
        if m.titre_litteraux:
            manquants = sum(1 for t in m.titre_litteraux if t not in titre)
            self.departage += len(m.titre_litteraux) if not manquants else -manquants


def _empreinte(r: LectureFiche) -> tuple:
    return (tuple(r.code_produit), tuple(r.remplace),
            tuple(tuple(e.references) for e in r.equivalentes), r.titre_liste,
            tuple((a.marque, a.ref_modele, a.nom) for a in r.appareils))


def _troncature(r: LectureFiche, modele: Optional[ModeleLecture]):
    """Liste réduite par la limite de caractères (§ 4.6) : motifs relevés."""
    motifs = r.motifs_troncature
    if modele and modele.max_caracteres and r.longueur_visible >= \
            _SEUIL_LIMITE * modele.max_caracteres:
        motifs.append('longueur_proche_limite')
    if r.marques and any(n.nature == 'marque_sans_appareil' and n.texte == r.marques[-1]
                         for n in r.non_compris):
        motifs.append('derniere_marque_vide')
    # Replis de l'export de l'outil (réf. seule ou nom seul sur toutes les lignes) ;
    # les anciennes fiches écrites à la main n'ont souvent que des réf. : pas un repli
    if r.sources.get('titre_liste') == 'profil' and len(r.appareils) >= 20 and \
            all(a.format == 'ref_seule' for a in r.appareils):
        motifs.append('lignes_sans_nom')
    r.liste_tronquee = bool(motifs)
    if motifs:
        r.non_compris.append(NonCompris('liste_tronquee', '', detail=', '.join(motifs)))


def lire_description(description: str, modeles: Iterable[ModeleLecture] = (),
                     marques_connues: Iterable[str] = (),
                     types_connus: Iterable[str] = (), marque_produit: str = '') -> LectureFiche:
    """
    Lit une description de fiche (HTML ou texte).

    modeles : modèles tirés des profils Fiche (modeles_depuis_config) ; tous sont
        essayés, le meilleur score l'emporte. Sans modèle : repérage par texte.
    marques_connues : marques de la base (indice supplémentaire, § 4.4).
    types_connus : types d'appareils de la base (« Four Vapeur » en fin de ligne
        ou sur la ligne suivante = type de l'appareil, pas une marque).
    marque_produit : marque du produit sur le site ; ses marques connues servent
        d'annonce quand la description n'en a pas.
    """
    blocs = normaliser(description)
    connues = {cle_marque(m) for m in marques_connues if m}
    types = {cle_marque(t) for t in types_connus if t}
    modeles = list(modeles)

    if not modeles:
        r = _Lecture(blocs, None, connues, types, marque_produit).lire()
        r.longueur_visible = longueur_visible(description)
        _troncature(r, None)
        return r

    # Une lecture par signature : les profils de même signature lisent pareil
    par_signature: Dict[tuple, _Lecture] = {}
    lectures: List[Tuple[_Lecture, ModeleLecture]] = []
    for modele in modeles:
        sig = modele.signature()
        if sig not in par_signature:
            par_signature[sig] = _Lecture(blocs, modele, connues, types, marque_produit)
            par_signature[sig].lire()
        lectures.append((par_signature[sig], modele))

    scores = [ScoreProfil(m.nom, len(lec.reconnus_profil), lec.departage,
                          sorted(set(lec.reconnus_profil))) for lec, m in lectures]
    meilleur = max((s.score, s.departage) for s in scores)
    en_tete = [(lec, m) for (lec, m), s in zip(lectures, scores)
               if (s.score, s.departage) == meilleur]
    lec, modele = en_tete[0]
    r = lec.r
    r.scores = scores
    r.longueur_visible = longueur_visible(description)
    if meilleur[0] == 0:
        r.profil = None          # aucun profil ne reconnaît rien : texte seul
    else:
        r.profil = modele.nom
        meme = [m.nom for _, m in en_tete if m.signature() == modele.signature()]
        r.profils_equivalents = [n for n in meme if n != modele.nom]
        autres = [(l, m) for l, m in en_tete if m.signature() != modele.signature()]
        if autres:
            r.profil_ambigu = True
            r.non_compris.append(NonCompris(
                'profil_ambigu', '', detail=', '.join([modele.nom] + [m.nom for _, m in autres])))
            if any(_empreinte(l.r) != _empreinte(r) for l, _ in autres):
                r.non_compris.append(NonCompris('lecture_divergente', ''))
    _troncature(r, modele if r.profil else None)
    return r
