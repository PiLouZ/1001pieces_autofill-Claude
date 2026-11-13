"""
Moteur de questions de l'import par lots (refonte de la reprise, étape 2)

Pur Python, sans Qt. À la place des catégories validées en bloc, un lot pose
des QUESTIONS en langage métier, chacune avec ses cas, des exemples et une
réponse proposée ; tout le reste est un récapitulatif sans décision (exacts,
déjà couverts, relations sans doute).

- Règles (posées une fois, mémorisées dans `regles_reprise` de
  data/reprise_fiches.json, révocables) :
  R1  même réf. sous une autre marque du groupe = même appareil ?
  (R2 « autre type sur le site » n'existe plus depuis le 2026-11-12 : même marque et
  même réf., c'est le même appareil, il est relié ; le type devient un écart.)
  R3  même nom commercial, réf. différente : nouvel appareil ?
  R4:<marque>|<marque>  même réf. sous une marque hors du groupe : même groupe ?
      (« oui » enrichit `groupes_marques` et demande de relire le lot)
  R5  réf. produit du site sans rapport avec le code produit : la garder ?
  R6  titre de la fiche différent du nom de la pièce : garder le nom de l'outil ?
  R7  pièce prise dans la réf. interne (pas de code produit) : la reprendre ?
- Questions du lot :
  Q1  créer les appareils inconnus (type et marque connus) ?
  Q2:<produit>  type des appareils à créer d'une fiche (proposé d'après la base)
  Q3:<produit>  marque des appareils à créer d'une fiche (proposée d'après la base)
  Q4:<forme>    équivalentes sans marque d'origine (étiquette, écarter, garder sans)
  Q5  remplacements en conflit avec l'existant
  Q6  EAN du site différent de l'outil ; Q7 réf. produit rattachée à une autre pièce
- Écarts (`ecarts`, clés « E:… ») : appareil connu dont un champ diffère sur la
  fiche (type, marque du groupe, écriture de la réf., nom commercial). Groupés
  par cas identiques (« type Lave-linge → Sèche-linge ») ; une réponse vaut pour
  tout le groupe, un choix sur une ligne l'emporte. Sans réponse, l'outil est
  gardé : un écart ne bloque jamais le lot. Un nom commercial vide dans l'outil
  est complété sans question.
- Sans question (« à revoir ») : appareil à choisir parmi plusieurs sans
  candidat de même réf., réf. illisible : ces lignes sont laissées de côté,
  leur fiche est signalée à revoir.

Garanties (CDC § 5.2, § 12 : tout doute est validé par l'utilisateur) :
- une ligne douteuse ne s'écrit que par la réponse à SA question ; tant
  qu'une question est sans réponse, le lot ne s'enregistre pas ;
- « accepter les propositions » ne répond jamais à une question sans proposition.

Les réponses se traduisent en choix individuels (`DecisionsFiche`) : le
planificateur de l'étape 3 reste le seul à décider de ce qui s'écrit.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from src.utils.lecteur_fiche.lecteur import cle_marque
from src.utils.rapprochement_fiche.acces_base import forme_normalisee
from src.utils.rapprochement_fiche.decisions import (
    ChoixAppareil, DecisionsFiche, VALIDEE, categorie_appareil, categorie_equivalence,
)
from src.utils.rapprochement_fiche.resultat import CHAMPS_ECARTS, Ecart

REGLE, LOT = 'regle', 'lot'
A_REVOIR = 'a_revoir'                   # ligne sans question, laissée de côté
ILLISIBLE = 'illisible'
DOUBLON = 'doublon'                     # même appareil cité deux fois : rien à écrire

TEXTES_REGLES = {
    'R1': ("Même référence sous une autre marque du même groupe : est-ce le même appareil ?",
           [('oui', "Oui, c'est le même appareil"), ('non', "Non, laisser ces appareils de côté")],
           'oui'),
    'R3': ("Même nom commercial qu'un appareil de l'outil, mais référence différente : "
           "est-ce un nouvel appareil ?",
           [('creer', "Oui, créer l'appareil"), ('non', "Non, laisser ces appareils de côté")],
           'creer'),
    'R5': ("La référence produit du site ne ressemble pas au code produit (code fournisseur…) : "
           "la garder pour l'export EveryParts ?",
           [('enregistrer', "Oui, garder la référence du site"),
            ('ignorer', "Non, ne pas enregistrer le produit du site")], 'enregistrer'),
    'R6': ("Le titre de la fiche diffère du nom de la pièce dans l'outil : quel nom garder ?",
           [('garder', "Garder le nom de l'outil"), ('prendre', "Prendre le titre du site")],
           'garder'),
    'R7': ("La fiche n'a pas de code produit : reprendre la pièce sous la référence produit "
           "du site ?",
           [('reprendre', "Oui, la reprendre"), ('de_cote', "Non, mettre la fiche à revoir")], None),
}
# Doute d'identité → (question, valeur du choix d'identité pour chaque réponse)
_IDENTITE = {
    'ref_interne_differente': ('R5', {'enregistrer': 'enregistrer', 'ignorer': 'ignorer'}),
    'libelle_different': ('R6', {'garder': 'garder', 'prendre': 'prendre'}),
    'ean_different': ('Q6', {'site': 'site', 'outil': 'outil'}),
    'ref_interne_autre_piece': ('Q7', {'prendre': 'prendre', 'garder': 'garder'}),
}


@dataclass
class Question:
    cle: str
    genre: str                          # REGLE ou LOT
    titre: str
    choix: List[Tuple[str, str]]        # (valeur, libellé)
    proposition: Optional[str] = None
    explication: str = ''
    libre: str = ''                     # réponse libre possible : 'type', 'marque', 'etiquette'
    occurrences: List[Tuple[int, object]] = field(default_factory=list)  # (fiche, ligne ou élément)
    exemples: List[str] = field(default_factory=list)
    reponse: Optional[str] = None
    memorisee: bool = False             # règle déjà posée à un lot précédent

    @property
    def repondue(self) -> bool:
        return self.reponse is not None

    @property
    def fiches(self) -> int:
        return len({i for i, _ in self.occurrences})

    @property
    def cas(self) -> int:
        return len(self.occurrences)

    def exemple(self, texte: str):
        if len(self.exemples) < 4 and texte not in self.exemples:
            self.exemples.append(texte)


@dataclass
class GroupeEcart:
    """Écarts identiques d'un lot (même champ ; même valeur outil → site pour le
    type et la marque) : une réponse ('outil' / 'site') vaut pour tous les cas."""
    cle: str
    champ: str
    outil: str = ''                     # '' : valeurs propres à chaque cas (réf., nom)
    site: str = ''
    cas: List[Tuple[int, int, Ecart]] = field(default_factory=list)   # (fiche, ligne, écart)
    reponse: Optional[str] = None
    choix: Dict[Tuple[int, int], str] = field(default_factory=dict)   # choix par ligne

    @property
    def titre(self) -> str:
        libelle = CHAMPS_ECARTS[self.champ][0]
        if self.outil or self.site:
            return f"{libelle} : {self.outil} dans l'outil, {self.site} sur le site"
        return f"{libelle} différent"

    def decision(self, i: int, k: int) -> Optional[str]:
        return self.choix.get((i, k), self.reponse)

    @property
    def fiches(self) -> int:
        return len({i for i, _, _ in self.cas})


def cle_ecart(e: Ecart) -> str:
    if e.champ in ('type', 'marque'):
        return f"E:{e.champ}:{e.outil}→{e.site}"
    return f"E:{e.champ}"


def _valeur(reponse: Optional[str], prefixe: str) -> str:
    """'type:Hotte' → 'Hotte' (réponse libre)."""
    if reponse and reponse.startswith(prefixe + ':'):
        return reponse.split(':', 1)[1].strip()
    return ''


class QuestionnaireLot:
    """Questions d'un lot, réponses, et leur traduction en décisions par fiche."""

    def __init__(self, lot, acces=None, config=None,
                 sauver_regles: Optional[Callable[[Dict[str, str]], None]] = None,
                 reponses: Optional[Dict[str, str]] = None):
        self.lot = lot
        self.acces = acces
        self.config = config
        self.sauver_regles = sauver_regles
        self.memorisees: Dict[str, str] = dict(getattr(config, 'regles', {}) or {})
        self.reponses: Dict[str, str] = dict(reponses or {})
        self.relire = False                 # groupes de marques modifiés : relire le lot
        # Choix faits ligne par ligne dans l'aperçu d'une fiche (index de fiche →
        # décisions partielles) : ils l'emportent sur les réponses et sortent les
        # éléments concernés des questions
        self.individuels: Dict[int, DecisionsFiche] = {}
        # Écarts : réponses par groupe (`reponses`, clés « E:… ») et choix par ligne
        self.choix_ecarts: Dict[Tuple[int, int, str], str] = {}
        self.ecarts: Dict[str, GroupeEcart] = {}
        self.questions: Dict[str, Question] = {}
        self.lignes: Dict[Tuple[int, int], str] = {}     # (fiche, ligne) → question ou A_REVOIR
        self.a_revoir: Dict[int, List[str]] = defaultdict(list)
        self.recapitulatif: Dict[str, int] = {}
        self._propositions: Dict[str, Optional[str]] = {}
        self.construire()

    # =========================================================================
    # Construction
    # =========================================================================
    def reponse(self, cle: str) -> Optional[str]:
        if cle in self.reponses:
            return self.reponses[cle]
        return self.memorisees.get(cle)

    def _question(self, cle: str) -> Question:
        q = self.questions.get(cle)
        if q is not None:
            return q
        if cle in TEXTES_REGLES:
            titre, choix, proposition = TEXTES_REGLES[cle]
            q = Question(cle, REGLE, titre, list(choix), proposition)
        elif cle.startswith('R4:'):
            marque, autre = cle[3:].split('|', 1)
            q = Question(cle, REGLE, f"La même référence existe sous {autre} : {autre} fait-il partie "
                                     f"du même groupe que {marque} ?",
                         [('oui', f"Oui, {autre} est du même groupe (relire le lot)"),
                          ('non', "Non, ce sont d'autres appareils")], None)
        elif cle == 'Q1':
            q = Question(cle, LOT, "Créer les appareils inconnus de l'outil ?",
                         [('creer', "Créer ces appareils"), ('de_cote', "Pas maintenant")], 'creer',
                         explication="Leur marque et leur type sont connus (en-tête, table du site, "
                                     "catégorie du produit).")
        elif cle.startswith('Q2:'):
            q = Question(cle, LOT, f"Type des appareils à créer de la fiche {cle[3:]}",
                         [('de_cote', "Laisser ces appareils de côté")], None, libre='type')
        elif cle.startswith('Q3:'):
            q = Question(cle, LOT, f"Marque des appareils à créer de la fiche {cle[3:]}",
                         [('de_cote', "Laisser ces appareils de côté")], None, libre='marque')
        elif cle.startswith('Q4:'):
            q = Question(cle, LOT, f"Équivalentes sans marque d'origine (forme {cle[3:]})",
                         [('sans', "Les garder sans marque d'origine"),
                          ('ecarter', "Les écarter (erreur de lecture)")], None, libre='etiquette')
        elif cle == 'Q5':
            q = Question(cle, LOT, "Remplacements en conflit : l'ancienne référence a déjà un autre "
                                   "successeur dans l'outil",
                         [('garder', "Garder l'existant"), ('prendre', "Prendre la fiche")], 'garder')
        elif cle == 'Q6':
            q = Question(cle, LOT, "Le code-barres (EAN) du site diffère de celui de l'outil",
                         [('site', "Prendre celui du site"), ('outil', "Garder celui de l'outil")],
                         'site')
        elif cle == 'Q7':
            q = Question(cle, LOT, "La référence produit du site est déjà rattachée à une autre pièce",
                         [('prendre', "La rattacher à la pièce de la fiche"),
                          ('garder', "La laisser à sa pièce actuelle")], 'prendre')
        else:
            raise KeyError(cle)
        if cle in self._propositions:
            q.proposition = self._propositions[cle]
        q.reponse = self.reponse(cle)
        q.memorisee = cle not in self.reponses and cle in self.memorisees
        self.questions[cle] = q
        return q

    def construire(self):
        self.questions, self.lignes, self.ecarts = {}, {}, {}
        self.a_revoir = defaultdict(list)
        recap: Counter = Counter()
        for i, f in self.lot.fiches_actives():
            if f.personnalisee:
                continue
            r = f.rapprochement
            ident = f'{f.id_produit}'
            ind = self.individuels.get(i)
            for k, a in enumerate(r.appareils):
                self._ecarts_ligne(i, k, a, ind, recap)
                if ind is not None and k in ind.appareils:
                    continue                # choisi dans l'aperçu de la fiche
                cle = self._cle_ligne(i, f, k, a, recap)
                if cle is None:
                    continue
                self.lignes[(i, k)] = cle
                if cle in (A_REVOIR, ILLISIBLE, DOUBLON):
                    continue
                q = self._question(cle)
                q.occurrences.append((i, k))
                q.exemple(self._exemple_ligne(ident, cle, a))
            self._identite(i, f, r)
            for rp in r.remplacements:
                if ind is not None and rp.ancienne in ind.remplacements:
                    continue
                if rp.statut == 'conflit':
                    q = self._question('Q5')
                    q.occurrences.append((i, rp.ancienne))
                    q.exemple(f"{ident} {rp.ancienne} : outil → {rp.successeur_actuel}, "
                              f"fiche → {rp.nouvelle}")
                elif rp.statut == 'nouveau':
                    recap['remplacements'] += 1
            for e in r.equivalences:
                if e.statut in ('deja_dans_le_groupe', 'dans_la_succession', 'ecartee'):
                    continue
                if ind is not None and (e.reference in ind.origines or e.reference in ind.ecartees):
                    continue
                if categorie_equivalence(e) == 'conflits':
                    from src.utils.rapprochement_fiche.decisions import forme_reference
                    cle = f"Q4:{forme_reference(e.reference)}"
                    if not any(c.isdigit() for c in e.reference):
                        self._propositions[cle] = 'ecarter'
                    q = self._question(cle)
                    if q.proposition is None and cle in self._propositions:
                        q.proposition = self._propositions[cle]
                    q.occurrences.append((i, e.reference))
                    q.exemple(f"{ident} {e.reference}")
                else:
                    recap['equivalentes'] += 1
            if f.profil_ambigu:
                recap['profils_ambigus'] += 1
        self._proposer_types_et_marques()
        self._proposer_origines()
        self._titres()
        self.recapitulatif = dict(recap)

    def _ecarts_ligne(self, i: int, k: int, a, ind: Optional[DecisionsFiche], recap: Counter):
        """Écarts d'une ligne qui désigne un appareil connu : seulement si la ligne
        sera reliée à CET appareil (exacte, normalisée, déjà liée ou couverte ; R1
        « oui » ; choix dans l'aperçu)."""
        if not a.ecarts:
            return
        choix = ind.appareils.get(k) if ind is not None else None
        if choix is not None:
            if choix.ignorer or choix.creer:
                return
            cible = choix.appareil_id
        elif categorie_appareil(a) in ('exacts', 'normalises', 'deja_couverts'):
            cible = a.appareil_id
        elif a.motif in ('meme_ref_groupe', 'nom_meme_ref') and self.reponse('R1') == 'oui':
            c = self._meme_ref(a)
            cible = c.id if c is not None else None
        else:
            cible = None
        if cible is None:
            return
        for e in a.ecarts:
            if e.appareil_id != cible:
                continue
            if e.tranche:
                recap['ecarts_tranches'] += 1
                continue
            if e.a_completer:
                recap['noms_completes'] += 1
                continue
            cle = cle_ecart(e)
            g = self.ecarts.get(cle)
            if g is None:
                outil, site = (e.outil, e.site) if e.champ in ('type', 'marque') else ('', '')
                g = self.ecarts[cle] = GroupeEcart(cle, e.champ, outil, site,
                                                   reponse=self.reponses.get(cle))
            g.cas.append((i, k, e))
            individuel = (ind.champs.get((k, e.champ)) if ind is not None else None) \
                or self.choix_ecarts.get((i, k, e.champ))
            if individuel:
                g.choix[(i, k)] = individuel

    def liste_ecarts(self) -> List[GroupeEcart]:
        """Type et marque d'abord (les plus lourds de conséquences), puis par cas décroissants."""
        ordre = {'type': 0, 'marque': 1, 'ref': 2, 'nom': 3}
        return sorted(self.ecarts.values(), key=lambda g: (ordre[g.champ], -len(g.cas), g.cle))

    def _titres(self):
        """Titres lisibles des questions d'une fiche (nom de la fiche, références)."""
        for cle, q in self.questions.items():
            if not q.occurrences:
                continue
            f = self.lot.fiches[q.occurrences[0][0]]
            fiche = f"fiche {f.id_produit} « {f.nom[:70]} »" if f.nom else f"fiche {f.id_produit}"
            if cle.startswith('Q2:'):
                q.titre = f"{q.cas} appareil(s) sans type à créer · {fiche} : quel type ?"
            elif cle.startswith('Q3:'):
                annoncees = ', '.join(f.marques_annoncees) or 'aucune'
                q.titre = (f"{q.cas} appareil(s) à créer sans marque · {fiche} : quelle marque ? "
                           f"(la fiche annonce : {annoncees})")
            elif cle.startswith('Q4:'):
                refs = ', '.join(dict.fromkeys(str(e) for _, e in q.occurrences))
                q.titre = f"Équivalente(s) sans marque d'origine : {refs}"

    def _proposer_origines(self):
        """Équivalentes sans marque d'origine : si toutes leurs fiches n'annoncent
        qu'une seule et même marque (« Montage sur Bauknecht »), elle est proposée."""
        for cle, q in self.questions.items():
            if not cle.startswith('Q4:') or q.proposition is not None:
                continue
            marques = {tuple(self.lot.fiches[i].marques_annoncees) for i, _ in q.occurrences}
            if len(marques) == 1:
                (unique,) = marques
                if len(unique) == 1:
                    q.proposition = f"etiquette:{unique[0]}"
                    q.explication = f"Proposé : {unique[0]}, la seule marque annoncée par la fiche."


    def _cle_ligne(self, i, f, k, a, recap) -> Optional[str]:
        cat = categorie_appareil(a)
        if cat in ('exacts', 'normalises', 'deja_couverts'):
            recap[{'deja_lie': 'deja_liees', 'deja_couvert': 'deja_couvertes'}.get(a.lien, 'nouvelles')] += 1
            return None
        if cat == 'a_valider' and a.niveau != 'absent':   # absent à marque à choisir : création
            m = a.motif
            if m in ('meme_ref_groupe', 'nom_meme_ref'):
                return 'R1' if self._meme_ref(a) is not None else A_REVOIR
            if m == 'nom_ref_differente':
                return 'R3'
            return A_REVOIR                 # à choisir parmi plusieurs : à revoir
        # Absents et types manquants : création
        if a.motif == 'doublon_nom':
            recap['doublons'] += 1
            return DOUBLON
        if a.suspecte:
            recap['illisibles'] += 1
            return ILLISIBLE
        marque = a.marque or a.marque_fiche
        if a.hors_groupe and marque:
            cle = f"R4:{marque}|{a.hors_groupe[0]}"
            if self.reponse(cle) != 'non':
                return cle
        if not marque:
            reponse = self.reponse(f"Q3:{f.id_produit}")
            if not _valeur(reponse, 'marque'):
                return f"Q3:{f.id_produit}"
        if not a.type:
            reponse = self.reponse(f"Q2:{f.id_produit}")
            if not _valeur(reponse, 'type'):
                return f"Q2:{f.id_produit}"
        if a.marque and a.type:
            return 'Q1'
        # marque et type obtenus par Q3 / Q2 : leur réponse vaut création
        return f"Q2:{f.id_produit}" if not a.type else f"Q3:{f.id_produit}"

    def _exemple_ligne(self, ident: str, cle: str, a) -> str:
        texte = f"{ident} {a.marque or a.marque_fiche or ''} {a.ref_modele}".replace('  ', ' ')
        if a.nom:
            texte += f" « {a.nom} »"
        if cle == 'R1':
            c = self._meme_ref(a)
            if c is not None:
                texte += f" → trouvé sous {c.marque}"
        elif cle == 'R3' and a.candidats:
            c = a.candidats[0]
            texte += f" ≠ {c.marque} {c.ref_modele} de l'outil"
        return texte

    @staticmethod
    def _meme_ref(a):
        memes = [c for c in a.candidats
                 if forme_normalisee(c.ref_modele) == forme_normalisee(a.ref_modele)]
        if a.proposition is not None:
            memes = [c for c in memes if c.id == a.proposition] or memes
        return memes[0] if len(memes) == 1 else None

    def _identite(self, i, f, r):
        doutes = r.doutes_par_categorie()
        ind = self.individuels.get(i)
        for genre, (cle, _) in _IDENTITE.items():
            if genre in doutes and not (ind is not None and genre in ind.identite):
                q = self._question(cle)
                q.occurrences.append((i, genre))
                ident = r.identite
                q.exemple({'ref_interne_differente': f"{f.id_produit} : {ident.ref_interne} ≠ {ident.ref_piece}",
                           'libelle_different': f"{f.id_produit} : « {ident.libelle_outil} » / "
                                                f"« {ident.libelle} »",
                           'ean_different': f"{f.id_produit} : {ident.ean} ≠ {ident.ean_outil}",
                           'ref_interne_autre_piece': f"{f.id_produit} : {ident.ref_interne} → "
                                                      f"{ident.piece_du_produit}"}[genre])
        if 'code_produit_absent' in doutes:
            q = self._question('R7')
            q.occurrences.append((i, 'code_produit_absent'))
            q.exemple(f"{f.id_produit} : pièce {r.identite.ref_piece} « {f.nom[:50]} »")

    # --- Propositions de type et de marque (d'après la base) ---------------------
    def _proposer_types_et_marques(self):
        for cle, q in self.questions.items():
            if q.proposition is not None or not cle.startswith(('Q2:', 'Q3:')):
                continue
            lignes = [self.lot.fiches[i].rapprochement.appareils[k] for i, k in q.occurrences]
            if cle.startswith('Q2:'):
                t = self._type_propose(lignes)
                if t:
                    q.proposition = f"type:{t}"
                    q.explication = f"Proposé : {t}, le type des appareils de même marque et de " \
                                    f"même début de référence dans l'outil."
            else:
                m = self._marque_proposee(self.lot.fiches[q.occurrences[0][0]], lignes)
                if m:
                    q.proposition = f"marque:{m}"
                    q.explication = f"Proposé : {m}, la marque annoncée qui a le plus de " \
                                    f"références de même début dans l'outil."

    def _type_propose(self, lignes) -> str:
        if self.acces is None:
            return ''
        types: Counter = Counter()
        for a in lignes:
            marque = a.marque or a.marque_fiche
            forme = forme_normalisee(a.ref_modele)
            if not marque or len(forme) < 4:
                continue
            for c in self.acces.index_marque(marque).par_prefixe(forme[:4]):
                if c.type:
                    types[c.type] += 1
        if len(types) == 1 and sum(types.values()) >= 3:
            return next(iter(types))
        return ''

    def _marque_proposee(self, fiche, lignes) -> str:
        if self.acces is None:
            return ''
        annoncees = list(dict.fromkeys(fiche.marques_annoncees))
        if not annoncees:
            annoncees = sorted({c.marque for a in lignes for c in a.candidats if c.marque})
        if not annoncees:
            return ''
        scores: Counter = Counter()
        for m in annoncees:
            index = self.acces.index_marque(m)
            for a in lignes:
                forme = forme_normalisee(a.ref_modele)
                if len(forme) >= 6 and index.par_prefixe(forme[:6]):
                    scores[m] += 1
        if not scores:
            return ''
        (m1, n1), *reste = scores.most_common()
        if not reste or n1 >= 2 * reste[0][1]:
            return m1
        return ''

    # =========================================================================
    # Réponses
    # =========================================================================
    def liste(self) -> List[Question]:
        """Règles d'abord, puis questions du lot ; dans chaque genre, par cas décroissants."""
        return sorted(self.questions.values(),
                      key=lambda q: (q.genre != REGLE, q.memorisee, -q.cas, q.cle))

    def sans_reponse(self) -> List[Question]:
        return [q for q in self.liste() if not q.repondue]

    def repondre(self, cle: str, reponse: Optional[str], memoriser: bool = True):
        """Réponse à une question (None = la retirer). Une règle est mémorisée.

        Écarts : « E:… » répond pour tout le groupe (et efface ses choix par ligne) ;
        « E:…@fiche:ligne » choisit pour une seule ligne. Jamais mémorisé comme règle."""
        if cle.startswith('E:'):
            self._repondre_ecart(cle, reponse)
            self.construire()
            return
        if reponse is None:
            self.reponses.pop(cle, None)
            if cle in self.memorisees:
                self.memorisees.pop(cle)
                self._sauver()
        else:
            self.reponses[cle] = reponse
            if memoriser and (cle in TEXTES_REGLES or cle.startswith('R4:')):
                self.memorisees[cle] = reponse
                self._sauver()
            if cle.startswith('R4:') and reponse == 'oui':
                self.relire = True
        self.construire()

    def _repondre_ecart(self, cle: str, reponse: Optional[str]):
        groupe, _, ligne = cle.partition('@')
        g = self.ecarts.get(groupe)
        if ligne:
            i, k = (int(x) for x in ligne.split(':'))
            champ = groupe.split(':')[1]
            if reponse is None:
                self.choix_ecarts.pop((i, k, champ), None)
            else:
                self.choix_ecarts[(i, k, champ)] = reponse
            return
        if reponse is None:
            self.reponses.pop(groupe, None)
        else:
            self.reponses[groupe] = reponse
        if g is not None:
            for i, k, e in g.cas:
                self.choix_ecarts.pop((i, k, e.champ), None)

    def accepter_propositions(self) -> int:
        """Répond par sa proposition à chaque question qui en a une (jamais aux autres)."""
        n = 0
        for q in list(self.questions.values()):
            if not q.repondue and q.proposition is not None:
                self.repondre(q.cle, q.proposition)
                n += 1
        return n

    def _sauver(self):
        if self.sauver_regles is not None:
            self.sauver_regles(dict(self.memorisees))

    def en_attente(self) -> List[str]:
        out = [q.titre for q in self.sans_reponse()]
        if self.relire:
            out.insert(0, "Relire le lot : des marques ont été ajoutées à un groupe")
        return out

    # =========================================================================
    # Traduction en décisions
    # =========================================================================
    def appliquer(self):
        """Décisions de chaque fiche (non personnalisée) d'après les réponses."""
        lot = self.lot
        from src.utils.reprise_site.lot import CATEGORIES_LOT
        lot.etats = {c: VALIDEE for c in CATEGORIES_LOT}
        self.a_revoir = defaultdict(list)
        for i, f in lot.fiches_actives():
            if f.personnalisee:
                continue
            if f.de_cote and f.raison_de_cote.startswith('question'):
                f.de_cote, f.raison_de_cote = False, ''
            d = DecisionsFiche()
            f.decisions, f.lignes_auto = d, set()
            r = f.rapprochement
            for k, a in enumerate(r.appareils):
                cle = self.lignes.get((i, k))
                if cle is not None:
                    self._ligne(i, f, k, a, cle, d)
            self._decisions_identite(i, f, r, d)
            for g in self.ecarts.values():
                for i_, k, e in g.cas:
                    if i_ == i and g.decision(i, k):
                        d.champs[(k, e.champ)] = g.decision(i, k)
            for rp in r.remplacements:
                if rp.statut == 'conflit':
                    d.remplacements[rp.ancienne] = self.reponse('Q5') or 'garder'
            for e in r.equivalences:
                cle = next((c for c, q in self.questions.items() if c.startswith('Q4:')
                            and (i, e.reference) in q.occurrences), None)
                if cle is None:
                    continue
                rep = self.reponse(cle)
                if rep == 'ecarter':
                    d.ecartees.add(e.reference)
                elif _valeur(rep, 'etiquette'):
                    d.origines[e.reference] = _valeur(rep, 'etiquette')
                # « sans » : écrite sans marque d'origine ; sans réponse : le lot attend
            ind = self.individuels.get(i)
            if ind is not None:
                for k in ind.appareils:
                    f.lignes_auto.discard(k)
                d.appareils.update(ind.appareils)
                d.remplacements.update(ind.remplacements)
                d.origines.update(ind.origines)
                d.ecartees |= ind.ecartees
                d.identite.update(ind.identite)
                d.champs.update(ind.champs)

    def _ligne(self, i, f, k, a, cle, d: DecisionsFiche):
        def de_cote(raison):
            d.appareils[k] = ChoixAppareil(ignorer=True)
            f.lignes_auto.add(k)
            if raison:
                self.a_revoir[i].append(raison)

        if cle == A_REVOIR:
            de_cote(f"{a.marque or a.marque_fiche or '?'} {a.ref_modele} : appareil à choisir")
            return
        if cle == DOUBLON:
            d.appareils[k] = ChoixAppareil(ignorer=True)      # déjà cité : ni écrit ni à revoir
            return
        if cle == ILLISIBLE:
            de_cote(f"« {a.ref_modele} » : référence illisible")
            return
        rep = self.reponse(cle)
        if rep is None:
            de_cote('')                     # en attente : rien n'est écrit (le lot attend)
            return
        if cle == 'R1':
            if rep == 'oui':
                d.appareils[k] = ChoixAppareil(appareil_id=self._meme_ref(a).id)
            else:
                de_cote(f"{a.ref_modele} : même réf. sous une marque du groupe, non reliée")
            return
        if cle == 'R3':
            if rep == 'creer':
                d.appareils[k] = ChoixAppareil(creer=True, marque=a.marque or a.marque_fiche,
                                               type=a.type)
            else:
                de_cote(f"{a.ref_modele} : même nom commercial, non créé")
            return
        if cle.startswith('R4:'):
            de_cote('')                     # « oui » : le lot est à relire
            return
        if rep == 'de_cote':
            de_cote(f"{a.ref_modele} : création laissée de côté")
            return
        marque = (a.marque or a.marque_fiche
                  or _valeur(self.reponse(f"Q3:{f.id_produit}"), 'marque'))
        type_ = a.type or _valeur(self.reponse(f"Q2:{f.id_produit}"), 'type')
        d.appareils[k] = ChoixAppareil(creer=True, marque=marque, type=type_)

    def _decisions_identite(self, i, f, r, d: DecisionsFiche):
        doutes = r.doutes_par_categorie()
        for genre, (cle, valeurs) in _IDENTITE.items():
            if genre in doutes:
                rep = self.reponse(cle)
                if rep is not None:
                    d.identite[genre] = valeurs[rep]
        if 'code_produit_absent' in doutes and self.reponse('R7') == 'de_cote':
            f.de_cote, f.raison_de_cote = True, "question : pas de code produit"

    # =========================================================================
    def resume(self) -> Dict[str, int]:
        return {'regles': sum(1 for q in self.questions.values() if q.genre == REGLE),
                'regles_memorisees': sum(1 for q in self.questions.values() if q.memorisee),
                'questions_lot': sum(1 for q in self.questions.values() if q.genre == LOT),
                'sans_reponse': len(self.sans_reponse()),
                'lignes_a_revoir': sum(1 for c in self.lignes.values() if c == A_REVOIR),
                'lignes_illisibles': sum(1 for c in self.lignes.values() if c == ILLISIBLE)}
