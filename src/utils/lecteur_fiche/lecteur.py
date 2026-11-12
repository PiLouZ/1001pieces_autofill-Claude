"""
Lecteur de description de fiche produit (CDC import fiches site, § 4)

Transforme une description (HTML du site ou du back-office, ou texte collé)
en données structurées, SANS rien écrire et sans Qt :
- lecture guidée par tous les profils « Fiche » (score, meilleur profil, § 4.2),
  et repérage par texte en secours (anciens libellés compris) ;
- code produit, remplacements, lignes d'équivalentes (séparées, numérotées),
  marques (faisceau d'indices, § 4.4), lignes d'appareils (RÉF - NOM, anciens
  formats BSH « RÉF/01 NOM » et PNC Electrolux, § 4.5), liste tronquée (§ 4.6) ;
- ce qui n'a pas été compris (non_compris) alimente les doutes des étapes
  suivantes (rapprochement, aperçu).
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from src.utils.lecteur_fiche.modeles import ModeleLecture, Repere, cle_texte
from src.utils.lecteur_fiche.normalisation import Bloc, longueur_visible, normaliser

# --- Repérage par texte (secours) ---------------------------------------------
# Libellés connus, du plus précis au plus large. Toute variante rencontrée lors
# des mesures sur le site s'ajoute ici.
_REF = r"r[ée]f[ée]rences?"
LIBELLES_EQUIVALENTES = (
    re.compile(rf"^{_REF}\s+[ée]quivalentes?\s*:?\s*(.*)$", re.I),
)
LIBELLES_REMPLACE = (
    re.compile(rf"^remplacen?t?\s+(?:les\s+|la\s+)?(?:anciennes?\s+)?{_REF}\s*:?\s*(.*)$", re.I),
    re.compile(r"^remplacen?t?\s*:\s*(.*)$", re.I),
)
LIBELLES_CODE_PRODUIT = (
    re.compile(r"^code\s+produit\s*:?\s*(.*)$", re.I),
)
LIBELLE_COMPATIBLE_AVEC = re.compile(r"^compatible\s+avec\s*:?\s*(.*)$", re.I)
# Titres de liste (comparés sous forme cle_texte : minuscules, sans « : » final)
TITRES_LISTE = (
    re.compile(r"^(?:liste\s+des\s+)?appareils\s+compatibles(?:\s+avec\s+cette\s+pi[eè]ce)?$"),
    re.compile(r"^appareils\s+employant\s+cette\s+pi[eè]ce$"),
    re.compile(r"^mod[eè]les\s+compatibles$"),
)
SOUS_TITRE_NON_EXHAUSTIVE = re.compile(r"^\(?\s*liste\s+non\s+exhaustive\s*\)?$")
MESSAGE_TROP_VOLUMINEUX = "données trop volumineuses pour l'affichage"

# --- Lignes d'appareils (§ 4.5) -----------------------------------------------
_SEP_REF_NOM = ' - '
_BSH = re.compile(r"^(\S*[A-Za-z0-9]\S*/\d{1,2})\s+(\S.*)$")        # RÉF/01 NOM
_PNC_SERIE = re.compile(r"^\d{8,13}(?:\s+\d{8,13})+$")               # PNC alignés
_CHIFFRE = re.compile(r"\d")
_SEP_REFS = re.compile(r"[\s,;]+")

# Marque reconnue sans être annoncée ni connue : texte court, sans chiffre
_LONGUEUR_MAX_MARQUE = 40
# Part de la limite au-delà de laquelle une liste est probablement réduite
_SEUIL_LIMITE = 0.97


# =============================================================================
# Résultat
# =============================================================================

@dataclass
class LigneAppareil:
    numero: int                 # n° de ligne d'appareil dans la liste (1…)
    marque: Optional[str]       # marque de la section (None = avant toute marque)
    ref_modele: str
    nom: str                    # nom commercial, lu tel quel ('' si absent)
    format: str                 # 'ref_nom', 'bsh', 'pnc', 'ref_seule'
    bloc: int                   # index du bloc normalisé


@dataclass
class LigneEquivalentes:
    numero: int                 # n° de la ligne « Références équivalentes » (1…)
    references: List[str]
    bloc: int
    source: str                 # 'profil' ou 'texte'


@dataclass
class NonCompris:
    nature: str                 # cf. NATURES_NON_COMPRIS
    texte: str
    bloc: Optional[int] = None
    detail: str = ''


NATURES_NON_COMPRIS = {
    'bloc_non_lu': "bloc de l'en-tête non reconnu",
    'ligne_non_lue': "ligne de la liste non reconnue",
    'marque_inconnue': "marque ni annoncée ni connue",
    'appareil_sans_marque': "appareil avant toute marque",
    'marque_sans_appareil': "marque sans appareil",
    'marque_annoncee_absente': "marque de « Compatible avec » absente de la liste",
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
    code_produit: List[str] = field(default_factory=list)
    remplace: List[str] = field(default_factory=list)
    equivalentes: List[LigneEquivalentes] = field(default_factory=list)
    titre_liste: str = ''
    liste_non_exhaustive: bool = False
    marques: List[str] = field(default_factory=list)     # sections, dans l'ordre
    appareils: List[LigneAppareil] = field(default_factory=list)
    informations: List[str] = field(default_factory=list)
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

def decouper_references(valeur: str, separateur: str = ' ') -> List[str]:
    """« A B, C » → ['A', 'B', 'C'] (séparateur du profil, espaces, virgules, ;)."""
    if separateur and separateur.strip():
        valeur = valeur.replace(separateur, ' ')
    return [r for r in _SEP_REFS.split(valeur or '') if r]


def _premier(motifs: Sequence[re.Pattern], texte: str) -> Optional[str]:
    for motif in motifs:
        m = motif.match(texte)
        if m:
            return m.group(1).strip()
    return None


class _Lecture:
    """Une lecture de la fiche avec un modèle (ou aucun : texte seul)."""

    def __init__(self, blocs: List[Bloc], modele: Optional[ModeleLecture],
                 marques_connues: Set[str]):
        self.blocs = blocs
        self.modele = modele
        self.marques_connues = marques_connues
        self.r = LectureFiche()
        self.reconnus_profil: List[str] = []
        self.departage = 0

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
            refs = decouper_references(v, sep)
            self.r.equivalentes.append(LigneEquivalentes(
                len(self.r.equivalentes) + 1, refs, bloc.index, src))
            self._noter('equivalentes', src, bloc, self._libelle(bloc, v))
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

    def _titre_liste(self, bloc: Bloc) -> Optional[str]:
        m = self.modele
        cle = cle_texte(bloc.texte)
        if m and m.titres_liste and cle == m.titres_liste[0]:
            return 'profil'
        if any(t.match(cle) for t in TITRES_LISTE):
            return 'texte'
        return None

    # --- Marques ----------------------------------------------------------------
    def _connue(self, texte: str) -> bool:
        cle = texte.casefold()
        return cle in self.annoncees or cle in self.marques_connues

    def _est_marque(self, bloc: Bloc) -> Optional[bool]:
        """None = pas une marque ; True = marque reconnue ; False = marque inconnue."""
        texte = bloc.texte
        if _SEP_REF_NOM in texte:
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
    def _appareils(self, bloc: Bloc, marque: Optional[str]) -> List[Tuple[str, str, str]]:
        texte = bloc.texte
        if _SEP_REF_NOM in texte:
            ref, _, nom = texte.partition(_SEP_REF_NOM)
            ref, nom = ref.strip(), nom.strip()
            return [(ref, nom, 'ref_nom')] if ref else []
        if _PNC_SERIE.match(texte):
            return [(pnc, '', 'pnc') for pnc in texte.split()]
        m = _BSH.match(texte)
        if m:
            return [(m.group(1), m.group(2).strip(), 'bsh')]
        if _CHIFFRE.search(texte):
            return [(texte, '', 'ref_seule')]
        return []

    def _ajouter_appareils(self, bloc: Bloc, marque: Optional[str]) -> bool:
        lignes = self._appareils(bloc, marque)
        for ref, nom, fmt in lignes:
            self.r.appareils.append(LigneAppareil(len(self.r.appareils) + 1, marque, ref,
                                                  nom, fmt, bloc.index))
        if lignes and marque is None:
            self.r.non_compris.append(NonCompris('appareil_sans_marque', bloc.texte, bloc.index))
        return bool(lignes)

    # --- Déroulé -------------------------------------------------------------------
    def lire(self) -> LectureFiche:
        r = self.r
        blocs = self.blocs
        # Marques annoncées (« Compatible avec ») d'abord : indice pour la liste
        self.annoncees: Set[str] = set()
        for bloc in blocs:
            m = LIBELLE_COMPATIBLE_AVEC.match(bloc.texte)
            if m:
                noms = list(bloc.liens) or m.group(1).split()
                r.marques_annoncees = [n for n in noms if n]
                self.annoncees = {n.casefold() for n in r.marques_annoncees}
                break

        dans_liste = False
        marque: Optional[str] = None
        nb_par_marque: Dict[str, int] = {}
        classes_liste = self.modele.classes_liste if self.modele else frozenset()
        for bloc in blocs:
            texte = bloc.texte
            if LIBELLE_COMPATIBLE_AVEC.match(texte):
                continue
            if self._ligne_references(bloc):
                continue
            src = self._titre_liste(bloc)
            if src and not r.titre_liste:
                r.titre_liste = texte.rstrip(' :')
                self._noter('titre_liste', src, bloc, texte)
                dans_liste = True
                continue
            cle = cle_texte(texte)
            if SOUS_TITRE_NON_EXHAUSTIVE.match(cle):
                r.liste_non_exhaustive = True
                continue
            if MESSAGE_TROP_VOLUMINEUX in cle:
                r.motifs_troncature.append('message_trop_volumineux')
                continue
            if 'alert' in ' '.join(bloc.classes | bloc.classes_parents):
                r.informations.append(texte)        # bloc « Informations » du profil
                continue
            if not dans_liste:
                # Début de liste sans titre : bloc dans le conteneur de liste ou
                # en-tête de marque portant un id
                debut = ((classes_liste and classes_liste & (bloc.classes_parents | bloc.classes))
                         or 'class_perso5' in bloc.classes_parents
                         or (bloc.id and self._est_marque(bloc) is not None))
                if debut:
                    dans_liste = True
                    r.non_compris.append(NonCompris('liste_sans_titre', texte, bloc.index))
            if not dans_liste:
                if not r.titre and bloc.balise in ('h1', 'h2', 'h3'):
                    r.titre = texte
                else:
                    r.non_compris.append(NonCompris('bloc_non_lu', texte, bloc.index))
                continue
            # Dans la liste : marque, puis ligne d'appareil
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
            if self._ajouter_appareils(bloc, marque):
                if marque is not None:
                    nb_par_marque[marque] += len(r.appareils) - avant
                continue
            r.non_compris.append(NonCompris('ligne_non_lue', texte, bloc.index))

        for nom, nb in nb_par_marque.items():
            if nb == 0:
                r.non_compris.append(NonCompris('marque_sans_appareil', nom))
        if r.marques:
            presentes = {m.casefold() for m in r.marques}
            for nom in r.marques_annoncees:
                if nom.casefold() not in presentes:
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
        # Titre : tous les textes fixes du gabarit Titre présents dans le titre
        titre = cle_texte(self.r.titre)
        if m.titre_litteraux and titre and all(t in titre for t in m.titre_litteraux):
            self.departage += len(m.titre_litteraux)


def _empreinte(r: LectureFiche) -> tuple:
    return (tuple(r.code_produit), tuple(r.remplace),
            tuple(tuple(e.references) for e in r.equivalentes), r.titre_liste,
            tuple((a.marque, a.ref_modele, a.nom) for a in r.appareils))


def _troncature(r: LectureFiche, html_source: str, modele: Optional[ModeleLecture]):
    """Liste réduite par la limite de caractères (§ 4.6) : motifs relevés."""
    motifs = r.motifs_troncature
    if modele and modele.max_caracteres and r.longueur_visible >= \
            _SEUIL_LIMITE * modele.max_caracteres:
        motifs.append('longueur_proche_limite')
    if r.marques and any(n.nature == 'marque_sans_appareil' and n.texte == r.marques[-1]
                         for n in r.non_compris):
        motifs.append('derniere_marque_vide')
    # Stratégies de repli de l'export : réf. seule ou nom seul sur toutes les lignes
    if len(r.appareils) >= 20 and all(a.format == 'ref_seule' for a in r.appareils):
        motifs.append('lignes_sans_nom')
    r.liste_tronquee = bool(motifs)
    if motifs:
        r.non_compris.append(NonCompris('liste_tronquee', '', detail=', '.join(motifs)))


def lire_description(description: str, modeles: Iterable[ModeleLecture] = (),
                     marques_connues: Iterable[str] = ()) -> LectureFiche:
    """
    Lit une description de fiche (HTML ou texte).

    modeles : modèles tirés des profils Fiche (modeles_depuis_config) ; tous sont
        essayés, le meilleur score l'emporte. Sans modèle : repérage par texte.
    marques_connues : marques de la base (indice supplémentaire, § 4.4).
    """
    blocs = normaliser(description)
    connues = {m.casefold() for m in marques_connues if m}
    modeles = list(modeles)

    lectures: List[Tuple[_Lecture, ModeleLecture]] = []
    for modele in modeles:
        lec = _Lecture(blocs, modele, connues)
        lec.lire()
        lectures.append((lec, modele))

    if not lectures:
        r = _Lecture(blocs, None, connues).lire()
        r.longueur_visible = longueur_visible(description)
        _troncature(r, description, None)
        return r

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
    _troncature(r, description, modele if r.profil else None)
    return r
