"""
Fichiers MySpace d'Agora : chargement en local et famille d'une référence.

Fichiers (texte à largeur fixe, Latin-1), un par constructeur Agora, en `.zip`
ou déjà extraits (`Parts_3.zip` / `Parts_3.txt` : constructeur 3 = Electrolux) :
- pièces (87 car.) : réf. 0-18 | réf. liée (remplacement) 18-36 | désignation
  36-68 | commandable 68 (0/1) | statut 69-87 ;
- produits : réf. technique 0-18 | réf. commerciale 18-36 | code marque 36-40 |
  marque 40-88 | pays 88-90 | désignation 90-130.

Ni prix, ni appareils compatibles, ni photos : ceux-là viennent de l'API.
Le chargement remplace les tables MySpace de `agora.db` en une transaction.
"""

import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from .stockage import BaseAgora, cle_ref

# Constructeurs Agora (identifiant de l'API = n° des fichiers MySpace)
CONSTRUCTEURS: Dict[int, str] = {
    1: 'Brandt', 2: 'Whirlpool', 3: 'Electrolux', 4: 'BSH', 5: 'Miele',
    10: 'Autres marques', 17: 'Beko', 22: 'Liebherr / Falmec / Asko', 33: 'Candy / Hoover',
    37: 'Liebherr',
}
# Constructeurs sans fichier MySpace : l'API répond, les fichiers ne disent rien
SANS_FICHIER = {33}

# Code générique Whirlpool « ARTICLE EPUISE » : des centaines de pièces y renvoient,
# ce n'est pas un remplacement
# (« ARTICLE EPUISE » dans le fichier Whirlpool, « PART NO LONGER AVAILABLE » chez Beko)
_EPUISE = re.compile(r'ARTICLE\s+EPUIS|NO\s+LONGER\s+AVAILABLE', re.I)
CODES_EPUISE = {'481299999990'}
ANCIENNES_MAX = 60          # au-delà, ce n'est plus une famille mais un code générique


def est_code_epuise(piece: 'PieceMySpace') -> bool:
    return cle_ref(piece.ref) in CODES_EPUISE or bool(_EPUISE.search(piece.designation or ''))

_FICHIER = re.compile(r'^(Parts|Products)_(\d+)\.(zip|txt)$', re.I)

# Statuts relevés dans les fichiers (casse ignorée)
_FIN_DE_VIE = {'abandonnée', 'abandonnée - garan', 'obsolete', 'plus livrable', 'inactive',
               'abandonned'}
_RUPTURE = {'rupture', 'en rupture', 'epuisée', 'épuisée'}

COMMANDABLE, RUPTURE, REMPLACEE, NON_COMMANDABLE, FIN_DE_VIE = (
    'commandable', 'rupture', 'remplacée', 'non commandable', 'fin de vie')
_ORDRE = {COMMANDABLE: 0, RUPTURE: 1, REMPLACEE: 2, NON_COMMANDABLE: 3, FIN_DE_VIE: 4}


def etat_piece(statut: str, commandable: Optional[int]) -> str:
    s = (statut or '').strip().lower()
    if s in _FIN_DE_VIE:
        return FIN_DE_VIE
    if s.startswith('remplac'):
        return REMPLACEE
    if s in _RUPTURE:
        return RUPTURE
    if commandable == 1:
        return COMMANDABLE
    return NON_COMMANDABLE


_INDESIT = re.compile(r'C00\d{6}', re.I)
GROUPES_ASSOCIES = {2, 17}         # Whirlpool, Beko : presque toujours une jumelle Indesit C00…


def reference_associee(courante: 'PieceMySpace', anciennes: List[str]) -> Optional[str]:
    """La 1ʳᵉ ancienne référence de l'autre numérotation (C00… d'un côté, Whirlpool ou
    Beko de l'autre) : c'est une référence jumelle, pas un remplacement."""
    if courante is None or courante.constructeur not in GROUPES_ASSOCIES:
        return None
    courante_indesit = bool(_INDESIT.fullmatch(courante.ref_publiee))
    return next((r for r in anciennes if bool(_INDESIT.fullmatch(r)) != courante_indesit), None)


def ref_affichee(ref: str) -> str:
    """Référence telle qu'on la publie : sans espace (« 00 123 » → « 00123 »)."""
    return re.sub(r'\s+', '', ref or '')


# --- Chargement -----------------------------------------------------------------------

def fichiers_myspace(dossier: str) -> List[Tuple[str, int, str]]:
    """(genre « Parts » / « Products », constructeur, chemin) des fichiers reconnus.
    Un `.txt` extrait l'emporte sur le `.zip` du même nom."""
    trouves: Dict[Tuple[str, int], str] = {}
    for racine, _dirs, noms in os.walk(dossier):
        for nom in sorted(noms):
            m = _FICHIER.match(nom)
            if not m:
                continue
            cle = (m.group(1).capitalize(), int(m.group(2)))
            if cle not in trouves or nom.lower().endswith('.txt'):
                trouves[cle] = os.path.join(racine, nom)
    return [(g, n, chemin) for (g, n), chemin in sorted(trouves.items())]


def _lignes(chemin: str) -> Iterator[str]:
    if chemin.lower().endswith('.zip'):
        with zipfile.ZipFile(chemin) as z:
            for membre in z.namelist():
                if membre.lower().endswith('.txt'):
                    with z.open(membre) as brut:
                        for ligne in io.TextIOWrapper(brut, encoding='latin-1', newline=''):
                            yield ligne.rstrip('\r\n')
    else:
        with open(chemin, encoding='latin-1', newline='') as f:
            for ligne in f:
                yield ligne.rstrip('\r\n')


def lire_piece(ligne: str, constructeur: int) -> Optional[tuple]:
    if len(ligne) < 69:
        return None
    ref, liee = ligne[0:18].strip(), ligne[18:36].strip()
    if not ref:
        return None
    cmd = int(ligne[68]) if ligne[68].isdigit() else None
    return (constructeur, ref, cle_ref(ref), liee, cle_ref(liee), ligne[36:68].strip(), cmd,
            ligne[69:87].strip())


def lire_produit(ligne: str, constructeur: int) -> Optional[tuple]:
    if len(ligne) < 36:
        return None
    tech, com = ligne[0:18].strip(), ligne[18:36].strip()
    if not tech and not com:
        return None
    return (constructeur, tech, com, cle_ref(tech), cle_ref(com), ligne[36:40].strip(),
            ligne[40:88].strip(), ligne[88:90].strip(), ligne[90:130].strip())


def charger_dossier(base: BaseAgora, dossier: str,
                    progression: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
    """Charge tous les fichiers MySpace d'un dossier dans `agora.db` (remplace le
    chargement précédent). Retourne le nombre de lignes par fichier."""
    fichiers = fichiers_myspace(dossier)
    if not fichiers:
        raise ValueError("aucun fichier MySpace (Parts_N / Products_N, .zip ou .txt) dans ce dossier")
    comptes: Dict[str, int] = {}
    with base.connexion() as c:
        c.executescript("""
            DROP TABLE IF EXISTS myspace_pieces;
            DROP TABLE IF EXISTS myspace_produits;
            CREATE TABLE myspace_pieces (constructeur INTEGER, ref TEXT, ref_cle TEXT,
                ref_liee TEXT, ref_liee_cle TEXT, designation TEXT, commandable INTEGER, statut TEXT);
            CREATE TABLE myspace_produits (constructeur INTEGER, ref_tech TEXT, ref_com TEXT,
                ref_tech_cle TEXT, ref_com_cle TEXT, code_marque TEXT, marque TEXT, pays TEXT,
                designation TEXT);
        """)
        for genre, constructeur, chemin in fichiers:
            if progression:
                progression(f"{os.path.basename(chemin)}…")
            lire, table, n_col = ((lire_piece, 'myspace_pieces', 8) if genre == 'Parts'
                                  else (lire_produit, 'myspace_produits', 9))
            requete = f"INSERT INTO {table} VALUES ({','.join('?' * n_col)})"
            paquet, total = [], 0
            for ligne in _lignes(chemin):
                t = lire(ligne, constructeur)
                if t:
                    paquet.append(t)
                if len(paquet) >= 50000:
                    c.executemany(requete, paquet)
                    total += len(paquet)
                    paquet = []
            c.executemany(requete, paquet)
            comptes[os.path.basename(chemin)] = total + len(paquet)
        if progression:
            progression("Index…")
        c.executescript("""
            CREATE INDEX idx_ms_pieces_ref ON myspace_pieces(ref_cle);
            CREATE INDEX idx_ms_pieces_liee ON myspace_pieces(ref_liee_cle);
            CREATE INDEX idx_ms_produits_tech ON myspace_produits(ref_tech_cle);
            CREATE INDEX idx_ms_produits_com ON myspace_produits(ref_com_cle);
        """)
        base.ecrire_meta(c, 'charge_le', datetime.now(timezone.utc).isoformat(timespec='seconds'))
        base.ecrire_meta(c, 'dossier', dossier)
    return comptes


def myspace_charge(base: BaseAgora) -> bool:
    with base.connexion() as c:
        return c.execute("SELECT 1 FROM sqlite_master WHERE name = 'myspace_pieces'").fetchone() is not None


# --- Famille d'une référence ------------------------------------------------------------

@dataclass
class PieceMySpace:
    constructeur: int
    ref: str
    ref_liee: str
    designation: str
    commandable: Optional[int]
    statut: str

    @property
    def etat(self) -> str:
        return etat_piece(self.statut, self.commandable)

    @property
    def ref_publiee(self) -> str:
        return ref_affichee(self.ref)

    @property
    def nom_constructeur(self) -> str:
        return CONSTRUCTEURS.get(self.constructeur, f"constructeur {self.constructeur}")


@dataclass
class FamilleAgora:
    """Ce que les fichiers MySpace disent d'une référence saisie."""
    saisie: str
    courante: Optional[PieceMySpace] = None          # référence à publier
    chaine: List[PieceMySpace] = field(default_factory=list)   # saisie → … → courante
    anciennes: List[str] = field(default_factory=list)          # remplacées par la courante
    autres_constructeurs: List[int] = field(default_factory=list)
    epuisee: bool = False            # renvoie au code générique « article épuisé »
    # Référence jumelle Whirlpool / Beko ↔ Indesit (C00…) de la courante : Agora la
    # présente comme remplacée, l'outil la garde en « référence associée » (§ 10.17)
    associee: Optional[str] = None

    @property
    def trouvee(self) -> bool:
        return self.courante is not None

    @property
    def references(self) -> List[str]:
        """Toutes les références de la famille : la courante, sa jumelle, les anciennes."""
        refs = [self.courante.ref_publiee] if self.courante else []
        for r in ([self.associee] if self.associee else []) + self.anciennes:
            if r not in refs:
                refs.append(r)
        return refs


class FamillesMySpace:
    """Recherche dans les fichiers MySpace chargés (aucun appel à l'API)."""

    PROFONDEUR = 8

    def __init__(self, base: BaseAgora):
        self.base = base

    def _pieces(self, c, cle: str) -> List[PieceMySpace]:
        rows = c.execute("SELECT constructeur, ref, ref_liee, designation, commandable, statut "
                         "FROM myspace_pieces WHERE ref_cle = ?", (cle,)).fetchall()
        return [PieceMySpace(*r) for r in rows]

    def _meilleure(self, c, cle: str, prefere: Optional[int]) -> Optional[PieceMySpace]:
        pieces = self._pieces(c, cle)
        if not pieces:
            return None
        pieces.sort(key=lambda p: (p.constructeur != prefere, _ORDRE[p.etat]))
        return pieces[0]

    def famille(self, saisie: str, constructeur: Optional[int] = None) -> FamilleAgora:
        """Famille d'une référence. Sans constructeur imposé, chaque constructeur
        qui connaît la référence est essayé et le meilleur résultat l'emporte :
        une ligne Whirlpool vide ne doit pas masquer le remplacement donné par
        le fichier Beko (4346040285 → C00866459)."""
        cle = cle_ref(saisie)
        if not cle or not myspace_charge(self.base):
            return FamilleAgora(saisie=saisie.strip())
        with self.base.connexion() as c:
            tous = sorted({p.constructeur for p in self._pieces(c, cle)})
            if not tous:
                return FamilleAgora(saisie=saisie.strip())
            essais = [constructeur] if constructeur is not None else tous
            familles = [self._famille(c, saisie, cle, n) for n in essais]
        meilleure = min(familles, key=self._rang)
        retenu = meilleure.courante.constructeur if meilleure.courante else None
        meilleure.autres_constructeurs = [n for n in tous if n != retenu]
        return meilleure

    @staticmethod
    def _rang(f: FamilleAgora) -> tuple:
        """Ordre de préférence : pièce disponible, désignation renseignée, puis
        chaîne la plus longue (les remplacements sont connus)."""
        if f.courante is None:
            return (9, 1, 0)
        if f.epuisee and f.courante.etat not in (COMMANDABLE, RUPTURE):
            return (8, 1, 0)
        return (_ORDRE[f.courante.etat], 0 if f.courante.designation else 1,
                -(len(f.chaine) + len(f.anciennes)))

    def _famille(self, c, saisie: str, cle: str, constructeur: Optional[int]) -> FamilleAgora:
        f = FamilleAgora(saisie=saisie.strip())
        depart = self._meilleure(c, cle, constructeur)
        if depart is None:
            return f
        if est_code_epuise(depart):
            f.epuisee = True
            return f
        # Vers l'avant : on suit la référence liée tant que la pièce n'est pas commandable
        chaine, vues, p = [depart], {cle}, depart
        while (p.etat not in (COMMANDABLE, RUPTURE) and cle_ref(p.ref_liee)
               and cle_ref(p.ref_liee) not in vues and len(chaine) < self.PROFONDEUR):
            suivante = self._meilleure(c, cle_ref(p.ref_liee), p.constructeur)
            if suivante is None or est_code_epuise(suivante):
                f.epuisee = suivante is not None
                break
            vues.add(cle_ref(suivante.ref))
            chaine.append(suivante)
            p = suivante
        f.chaine = chaine
        disponibles = [x for x in chaine if x.etat in (COMMANDABLE, RUPTURE)]
        f.courante = disponibles[-1] if disponibles else chaine[-1]
        # Vers l'arrière : pièces remplacées par une référence de la chaîne
        anciennes = [x.ref_publiee for x in chaine if x is not f.courante]
        a_voir = [cle_ref(x.ref) for x in chaine]
        vues_arriere = set(a_voir)
        while a_voir and len(anciennes) < ANCIENNES_MAX:
            cible = a_voir.pop(0)
            for r in c.execute("SELECT ref, statut, commandable FROM myspace_pieces "
                               "WHERE ref_liee_cle = ? AND constructeur = ? LIMIT ?",
                               (cible, f.courante.constructeur, ANCIENNES_MAX + 1)):
                k = cle_ref(r[0])
                if k in vues_arriere or etat_piece(r[1], r[2]) in (COMMANDABLE, RUPTURE):
                    continue
                vues_arriere.add(k)
                anciennes.append(ref_affichee(r[0]))
                a_voir.append(k)
                if len(anciennes) >= ANCIENNES_MAX:
                    break
        f.anciennes = [r for r in dict.fromkeys(anciennes) if r != f.courante.ref_publiee]
        f.associee = reference_associee(f.courante, f.anciennes)
        if f.associee:
            f.anciennes.remove(f.associee)
        return f

    def produits(self, appareils: List[Tuple[str, str]],
                 constructeur: Optional[int] = None) -> Dict[Tuple[str, str], Tuple[str, str]]:
        """(marque, désignation) des appareils (réf. technique, réf. commerciale)
        trouvés dans le référentiel produits, en une seule connexion."""
        resultat: Dict[Tuple[str, str], Tuple[str, str]] = {}
        if not myspace_charge(self.base):
            return resultat
        with self.base.connexion() as c:
            for tech, com in appareils:
                for colonne, valeur in (('ref_tech_cle', cle_ref(tech)), ('ref_com_cle', cle_ref(com))):
                    if not valeur:
                        continue
                    row = c.execute(
                        f"SELECT marque, designation FROM myspace_produits WHERE {colonne} = ? "
                        "ORDER BY (constructeur = ?) DESC, (marque != '') DESC LIMIT 1",
                        (valeur, constructeur or -1)).fetchone()
                    if row:
                        resultat[(tech, com)] = (row[0] or '', row[1] or '')
                        break
        return resultat
