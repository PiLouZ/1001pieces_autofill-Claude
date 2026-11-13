"""
Rapprochement d'une fiche lue avec la base, SANS RIEN ÉCRIRE (CDC § 5, étape 2)

Entrée : une LectureFiche (lecteur de l'étape 1) et, si la fiche vient d'une
page publique, sa PagePublique (référence interne, EAN, catégorie, table du
site). Sortie : un Rapprochement où chaque élément a son niveau et sa raison,
et où les doutes sont regroupés par catégorie, pour l'aperçu de l'étape 3.

- Identité (§ 5.1) : 1ʳᵉ réf. du code produit, référence interne en secours
  (préfixe retiré), comparaison réf. interne / code produit, pièce fantôme,
  EAN.
- Appareils (§ 5.2) : marque + réf. modèle, passe exacte puis ponctuation
  ignorée ; marque déduite parmi les marques annoncées ; lignée calculée une
  fois par fiche pour « déjà lié » / « déjà couvert » ; union avec la table du
  site (§ 5.7) ; type appareil par appareil (§ 5.6).
- Remplacements (§ 5.4) : appariement par la forme dans une paire
  Whirlpool/Indesit, vérification de la chaîne avant de signaler un conflit.
- Équivalences (§ 5.3, 5.5) : étiquette d'origine déduite du format.

Mémoires du § 9 (étape 3) : passées en paramètre (décisions sur les paires
d'écritures, références écartées, étiquettes choisies), ou lues dans la base
avec `memoires=True`, qui ajoute aussi la comparaison avec le produit du site
connu (réf. interne, EAN), le libellé de la pièce (titre de la fiche) et les
liens de provenance site absents de la fiche (§ 6.2).
"""

import re


from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from src.utils.lecteur_fiche.lecteur import LectureFiche, cle_marque
from src.utils.lecteur_fiche.page_publique import LigneTableSite, PagePublique, ean13_valide
from src.utils.rapprochement_fiche.acces_base import (
    AccesBaseLecture, AppareilBase, forme_normalisee,
)
from src.utils.rapprochement_fiche.configuration import (
    ConfigurationRapprochement, charger_configuration,
)
from src.utils.rapprochement_fiche.resultat import (
    AppareilRapproche, Doute, Ecart, Equivalence, Identite, Rapprochement, Remplacement,
)

# Décision mémorisée sur une paire d'écritures (§ 9) : (clé de marque, {A, B}) → 'meme'/'distinct'
DecisionsPaires = Mapping[Tuple[str, FrozenSet[str]], str]

_TYPES_EXPLICITES = ('table', 'ligne')
_DOUTES_DE_CHOIX = ('normalise_ambigu', 'exact_multiple', 'a_valider', 'marque_a_choisir')
_MENTIONS_TITRE = re.compile(r"\(\s*photos?\s+non\s+contractuelles?\s*\)", re.I)


_CODE_LONG = re.compile(r"\d{9,}")


def _noms_differents(outil: str, site: str) -> bool:
    """Nom commercial du site à proposer à la place de celui de l'outil ?

    Non quand ils ne diffèrent que par la ponctuation, ou par un ou deux caractères
    en fin (indice de version : « AZB 82001 » sur le site, « AZB8200 » dans
    l'outil), ni quand le nom lu contient un code de 9 chiffres ou plus (liste
    d'appareils lue comme un nom : erreur de lecture). Mesure sur le 1ᵉʳ lot réel
    (2026-11-13) : 749 écarts → 166."""
    fo, fs = forme_normalisee(outil), forme_normalisee(site)
    if fo == fs or _CODE_LONG.search(site):
        return False
    if fo and (fs.startswith(fo) or fo.startswith(fs)) and abs(len(fs) - len(fo)) <= 2:
        return False
    return True


def libelle_titre_complet(titre: str) -> str:
    """Titre de la fiche sans « (photos non contractuelles) » : le libellé écrit
    avant la coupe au type d'appareil (reconnu à la relecture pour être remplacé)."""
    return re.sub(r"\s+", " ", _MENTIONS_TITRE.sub(' ', titre or '')).strip(' -–')


def libelle_depuis_titre(titre: str, appellations=None) -> str:
    """Libellé de la pièce tiré du titre de la fiche : ce qui précède « pour <type
    d'appareil> » (types et appellations de l'onglet Appareils). Ce qui suit le
    type est retiré (« (pièce générique) », « et cuisinière »), sauf une
    caractéristique chiffrée hors parenthèses, gardée à la suite (« Résistance
    pour sèche linge 1900W » → « Résistance 1900W »). Sans type reconnu : le
    titre entier. Le type n'est ainsi plus répété dans les exports."""
    from src.utils.rapprochement_fiche.coupe_titre import couper_au_type
    return couper_au_type(libelle_titre_complet(titre), appellations)


def rapprocher(lecture: LectureFiche, acces: AccesBaseLecture,
               config: Optional[ConfigurationRapprochement] = None,
               page: Optional[PagePublique] = None, *,
               ref_interne: str = '', ean: str = '', categorie: str = '',
               id_product: Optional[int] = None,
               table_site: Iterable[LigneTableSite] = (),
               decisions_paires: Optional[DecisionsPaires] = None,
               references_ecartees: Iterable[str] = (),
               origines_choisies: Optional[Mapping[str, str]] = None,
               memoires: bool = False) -> Rapprochement:
    """
    Rapproche une fiche lue avec la base (lecture seule).

    page : page publique de la fiche ; elle fournit la référence interne, l'EAN,
        la catégorie, l'id_product et la table du site quand les paramètres du
        même nom sont vides (export SQL : passer les colonnes de l'export).
    table_site : lignes de compatibilité du site (export SQL complet) ; sinon
        celles de la page (1ʳᵉ page seulement).
    origines_choisies : référence → étiquette d'origine choisie par l'utilisateur.
    memoires : lire en base les décisions consignées (complétées par les
        paramètres) et comparer la fiche au produit du site et à la pièce.
    """
    config = config or charger_configuration()
    if page is not None:
        ref_interne = ref_interne or page.ref_interne
        ean = ean or page.ean
        categorie = categorie or page.categorie
        id_product = id_product if id_product is not None else page.id_product
        table_site = list(table_site) or list(page.table_site)
    decisions = dict(acces.decisions_paires()) if memoires else {}
    decisions.update(decisions_paires or {})
    return _Rapprochement(lecture, acces, config, ref_interne, ean, categorie, id_product,
                          list(table_site), decisions, set(references_ecartees),
                          dict(origines_choisies or {}), memoires).executer()


class _Rapprochement:

    def __init__(self, lecture, acces, config, ref_interne, ean, categorie, id_product,
                 table_site, decisions_paires, ecartees, origines, memoires=False):
        self.l: LectureFiche = lecture
        self.acces: AccesBaseLecture = acces
        self.config: ConfigurationRapprochement = config
        self.ref_interne = (ref_interne or '').strip()
        self.ean = (ean or '').strip()
        self.categorie = categorie or ''
        self.id_product = id_product
        self.table_site: List[LigneTableSite] = table_site
        self.decisions = decisions_paires
        self.ecartees: Set[str] = ecartees
        self.origines_choisies: Dict[str, str] = origines
        self.memoires = memoires
        self.doutes: List[Doute] = []
        self.marques_outil = acces.marques()
        self.types_outil = acces.types()

    def _doute(self, categorie: str, message: str, element: str = ''):
        self.doutes.append(Doute(categorie, message, element))

    # =========================================================================
    def executer(self) -> Rapprochement:
        identite = self._identite()
        principale = identite.ref_piece
        if self.memoires and principale:
            self._charger_decisions(principale)
        refs_fiche = self._refs_fiche(principale)
        # Lignée calculée une fois par fiche : celle de la base pour la pièce
        # seule (relations existantes), et celle de toute la fiche (couverture)
        self.lignee_piece = self.acces.lignee([principale]) if principale else {}
        self.lignee = self.acces.lignee(refs_fiche) if refs_fiche else {}
        self._statut_ref_interne(identite)
        self.liens = self.acces.liens(self.lignee)

        r = Rapprochement(identite=identite, lignee=self.lignee,
                          liste_tronquee=self.l.liste_tronquee)
        r.remplacements = self._remplacements(principale) if principale else []
        r.equivalences = self._equivalences(principale) if principale else []
        r.appareils = self._appareils(principale)
        for nc in self.l.non_compris:
            self._doute('lecture', f"{nc.nature} : {nc.texte or nc.detail}".strip(' :'),
                        f"bloc:{nc.bloc}" if nc.bloc is not None else '')
        if self.memoires and principale:
            self._comparer_a_l_outil(identite)
            if not r.liste_tronquee:
                r.absents_de_la_fiche = self._absents_de_la_fiche(principale, r.appareils)
        r.doutes = self.doutes
        return r

    # =========================================================================
    # Mémoires de l'outil (§ 5.1, 5.8, 6.2, 9)
    # =========================================================================
    def _charger_decisions(self, principale: str):
        for ref, (nature, origine) in self.acces.decisions_references(principale).items():
            if nature == 'ecartee':
                self.ecartees.add(ref)
            elif origine:
                self.origines_choisies.setdefault(ref, origine)

    def _comparer_a_l_outil(self, i: Identite):
        # EAN (§ 5.1) : rangé avec le produit du site
        produits = self.acces.produit_site(self.ref_interne, self.id_product)
        par_ref = next((p for p in produits if p[0] == self.ref_interne), None)
        if self.ref_interne and par_ref is not None and par_ref[2] and par_ref[2] != i.ref_piece:
            i.piece_du_produit = par_ref[2]
            self._doute('ref_interne_autre_piece',
                        f"référence interne {self.ref_interne} rattachée à {par_ref[2]}, "
                        f"la fiche la donne à {i.ref_piece}", 'identite')
        if self.id_product is not None:
            autre = next((p for p in produits if p[1] == self.id_product
                          and p[0] != self.ref_interne), None)
            if autre is not None and self.ref_interne:
                i.ref_interne_precedente = autre[0]
        connu = par_ref if par_ref is not None else next(
            (p for p in produits if p[1] == self.id_product and self.id_product is not None), None)
        i.ean_outil = (connu[3] or '') if connu else ''
        if self.ean and i.statut_ean == 'valide':
            if not i.ean_outil:
                i.statut_ean_outil = 'a_remplir'
            elif i.ean_outil == self.ean:
                i.statut_ean_outil = 'identique'
            else:
                i.statut_ean_outil = 'different'
                self._doute('ean_different',
                            f"EAN {i.ean_outil} dans l'outil, {self.ean} sur le site", 'identite')
        # Libellé de la pièce : titre de la fiche
        i.libelle = libelle_depuis_titre(self.l.titre,
                                         getattr(self.config, 'appellations_appareils', None))
        i.libelle_outil = self.acces.libelle(i.ref_piece) if i.statut != 'absente' else ''
        if i.libelle:
            if not i.libelle_outil:
                i.statut_libelle = 'a_remplir'
            elif i.libelle_outil.strip() == i.libelle:
                i.statut_libelle = 'identique'
            elif i.libelle_outil.strip() == libelle_titre_complet(self.l.titre):
                # Écrit par une reprise antérieure, avant la coupe au type :
                # remplacé sans question (c'est le même titre)
                i.statut_libelle = 'ancienne_regle'
            else:
                i.statut_libelle = 'different'
                self._doute('libelle_different',
                            f"libellé « {i.libelle_outil} », fiche « {i.libelle} »", 'identite')

    def _absents_de_la_fiche(self, principale: str, appareils: List[AppareilRapproche]):
        # Un appareil de la fiche compte comme lu sous chacun de ses candidats
        lus = {a.appareil_id if a.appareil_id is not None else a.proposition for a in appareils}
        lus.update(c.id for a in appareils for c in a.candidats)
        return [app for app, _ in self.acces.liens_site(principale) if app.id not in lus]

    def _refs_fiche(self, principale: Optional[str]) -> List[str]:
        refs = [principale] if principale else []
        refs += self.l.code_produit[1:] + self.l.remplace + self.l.remplacee_par
        for ligne in self.l.equivalentes + self.l.references_par_marque:
            refs += ligne.references
        return list(dict.fromkeys(r for r in refs if r and r not in self.ecartees))

    # =========================================================================
    # Identité (§ 5.1)
    # =========================================================================
    def _identite(self) -> Identite:
        i = Identite(ref_interne=self.ref_interne, id_product=self.id_product, ean=self.ean)
        if self.l.reference_principale:
            i.ref_piece, i.source = self.l.reference_principale, 'code_produit'
        elif self.ref_interne:
            ref, prefixe = self.config.sans_prefixe(self.ref_interne)
            i.ref_piece, i.source, i.prefixe = ref, 'ref_interne', prefixe
            self._doute('code_produit_absent',
                        f"pièce {ref} prise dans la référence interne {self.ref_interne}",
                        'identite')
        if i.ref_piece:
            statut = self.acces.pieces([i.ref_piece]).get(i.ref_piece)
            if statut is None:
                i.statut = 'absente'
            else:
                i.statut = 'fantome' if statut.fantome else 'reelle'
                i.obsolete, i.piece_id = statut.obsolete, statut.id
        if self.ean:
            i.statut_ean = 'valide' if ean13_valide(self.ean) else 'cle_fausse'
            if i.statut_ean == 'cle_fausse':
                self._doute('ean_invalide', f"EAN {self.ean} : clé de contrôle fausse, non retenu",
                            'identite')
        return i

    def _statut_ref_interne(self, i: Identite):
        """Comparaison réf. interne / code produit, préfixe retiré (après la lignée)."""
        if not self.ref_interne or not i.ref_piece or i.source != 'code_produit':
            i.statut_ref_interne = 'prefixe' if i.prefixe else ''
            return
        if forme_normalisee(self.ref_interne) == forme_normalisee(i.ref_piece):
            i.statut_ref_interne = 'egale'      # à la ponctuation près (10-2930-5010)
            return
        _, prefixe = self.config.sans_prefixe(self.ref_interne, i.ref_piece)
        if prefixe:
            i.statut_ref_interne, i.prefixe = 'prefixe', prefixe
            return
        # Référence de la lignée (remplacée ou équivalente), préfixe retiré ou non
        for ref in self.lignee:
            if ref == i.ref_piece:
                continue
            if self.ref_interne.upper() == ref.upper():
                i.statut_ref_interne = 'lignee'
                return
            _, prefixe = self.config.sans_prefixe(self.ref_interne, ref)
            if prefixe:
                i.statut_ref_interne, i.prefixe = 'lignee', prefixe
                return
        i.statut_ref_interne = 'differente'
        self._doute('ref_interne_differente',
                    f"référence interne {self.ref_interne} ≠ code produit {i.ref_piece}",
                    'identite')

    # =========================================================================
    # Remplacements (§ 5.4)
    # =========================================================================
    def _remplacements(self, principale: str) -> List[Remplacement]:
        couples: List[Tuple[str, str, str, str]] = []
        cibles = self._cibles_par_origine()
        rangs = {ref: n for n, ref in enumerate(dict.fromkeys(self.l.remplace), 1)}
        for ancienne in dict.fromkeys(self.l.remplace):
            if len(self.l.code_produit) <= 1:
                couples.append((ancienne, principale, 'remplace', 'unique'))
                continue
            origine = self.config.origine(ancienne).etiquette
            if origine and origine in cibles:
                couples.append((ancienne, cibles[origine], 'remplace', 'forme'))
            else:
                couples.append((ancienne, principale, 'remplace', 'a_choisir'))
                self._doute('appariement',
                            f"{ancienne} : aucune référence de même forme dans le code produit "
                            f"({' '.join(self.l.code_produit)}), {principale} proposée",
                            f"remplacement:{ancienne}")
        for nouvelle in dict.fromkeys(self.l.remplacee_par):
            couples.append((principale, nouvelle, 'remplacee_par', 'unique'))

        anciennes = [a for a, *_ in couples]
        successeurs = self.acces.successeurs(anciennes)
        pieces = self.acces.pieces(anciennes)
        resultat = [self._remplacement(a, n, sens, app, successeurs, pieces)
                    for a, n, sens, app in couples]
        for r in resultat:
            if r.sens == 'remplace':
                r.rang = rangs.get(r.ancienne)
        return resultat

    def _cibles_par_origine(self) -> Dict[str, str]:
        """Origine → réf. du code produit, pour les origines portées par une seule réf."""
        par_origine: Dict[str, List[str]] = {}
        for ref in self.l.code_produit:
            o = self.config.origine(ref).etiquette
            if o:
                par_origine.setdefault(o, []).append(ref)
        return {o: refs[0] for o, refs in par_origine.items() if len(refs) == 1}

    def _remplacement(self, ancienne, nouvelle, sens, appariement, successeurs, pieces):
        r = Remplacement(ancienne, nouvelle, sens, appariement=appariement)
        element = f"remplacement:{ancienne}"
        if ancienne == nouvelle:
            r.statut, r.raison = 'identique', "même référence"
            return r
        chaine_nouvelle = self.acces.chaine(nouvelle)
        if ancienne in chaine_nouvelle:
            r.statut = 'cycle'
            r.raison = f"{' → '.join(chaine_nouvelle)} : {ancienne} est déjà après {nouvelle}"
            self._doute('remplacement_cycle', f"{ancienne} → {nouvelle} : {r.raison}", element)
            return r
        r.fantome_a_creer = ancienne not in pieces
        if ancienne not in successeurs or successeurs[ancienne] is None:
            r.statut = 'nouveau'
            r.raison = ("référence absente : fantôme à créer" if r.fantome_a_creer
                        else "pas encore de successeur")
            return r
        actuel = successeurs[ancienne]
        r.successeur_actuel = actuel
        if actuel == nouvelle:
            r.statut, r.raison = 'deja_present', "déjà en base"
            return r
        chaine_actuel = self.acces.chaine(actuel)
        if nouvelle in chaine_actuel:
            r.statut = 'confirme_par_chaine'
            r.raison = f"en base : {ancienne} → {' → '.join(chaine_actuel)}"
            return r
        if actuel in chaine_nouvelle:
            r.statut = 'confirme_par_chaine'
            r.raison = (f"en base : {ancienne} → {actuel}, et {' → '.join(chaine_nouvelle)} : "
                        f"la fiche est antérieure à la lignée")
            return r
        r.statut = 'conflit'
        r.raison = f"en base : {ancienne} → {' → '.join(chaine_actuel)}"
        self._doute('remplacement_conflit',
                    f"fiche : {ancienne} → {nouvelle} ; {r.raison}", element)
        return r

    # =========================================================================
    # Équivalences et étiquette d'origine (§ 5.3, 5.5)
    # =========================================================================
    def _equivalences(self, principale: str) -> List[Equivalence]:
        entrees: List[Tuple[str, str, int, str]] = [
            (ref, 'code_produit', 0, '') for ref in self.l.code_produit[1:]]
        for ligne in self.l.equivalentes:
            entrees += [(ref, 'equivalentes', ligne.numero, ligne.origine)
                        for ref in ligne.references]
            self._ligne_melangee(ligne.references, ligne.numero)
        for ligne in self.l.references_par_marque:
            entrees += [(ref, 'ref_marque', ligne.numero, ligne.origine)
                        for ref in ligne.references]
        vues: Set[str] = set()
        refs = [e[0] for e in entrees]
        groupes = self.acces.groupes(refs + [principale])
        groupe_piece = groupes.get(principale)
        succession = {r for r, rel in self.lignee_piece.items() if rel in ('depart', 'succession')}
        resultat = []
        for ref, source, numero, origine_fiche in entrees:
            if ref == principale or ref in vues:
                continue
            vues.add(ref)
            e = Equivalence(ref, source, numero)
            self._origine(e, origine_fiche)
            if ref in self.ecartees:
                e.statut, e.raison = 'ecartee', "écartée par l'utilisateur"
            elif ref in succession:
                e.statut, e.raison = 'dans_la_succession', "déjà dans la chaîne de remplacements"
            elif groupe_piece is not None and groupes.get(ref) == groupe_piece:
                e.statut, e.raison = 'deja_dans_le_groupe', f"groupe {groupe_piece}"
            elif groupe_piece is not None and groupes.get(ref) is not None:
                e.statut = 'fusion_groupes'
                e.raison = f"groupe {groupes[ref]} à fusionner avec le groupe {groupe_piece}"
            else:
                e.statut, e.raison = 'nouveau', "équivalence à créer"
            resultat.append(e)
        return resultat

    def _origine(self, e: Equivalence, origine_fiche: str):
        o = self.config.origine(e.reference)
        element = f"equivalence:{e.reference}"
        if origine_fiche:
            e.origine, e.source_origine = origine_fiche, 'fiche'
            return
        if self.origines_choisies.get(e.reference):
            e.origine, e.source_origine = self.origines_choisies[e.reference], 'decision'
            return
        if o.connue:
            e.origine, e.source_origine = o.etiquette, 'format'
        elif e.reference in self.ecartees:
            return                      # écartée : plus d'étiquette à demander
        elif o.doute:
            self._doute('origine_ambigue', f"{e.reference} : {o.doute}", element)
        else:
            self._doute('origine_inconnue', f"{e.reference} : format inconnu", element)

    def _ligne_melangee(self, refs: Sequence[str], numero: int):
        # Une paire du même groupe (Whirlpool / Indesit) n'est pas un mélange
        origines = {self.config.origine(r).etiquette for r in refs} - {''}
        if len({self.config.groupe_origine(o) for o in origines}) > 1:
            self._doute('ligne_melangee',
                        f"ligne {numero} : {' '.join(refs)} ({', '.join(sorted(origines))})",
                        f"ligne_equivalentes:{numero}")

    # =========================================================================
    # Appareils (§ 5.2, 5.6, 5.7)
    # =========================================================================
    def _appareils(self, principale: Optional[str]) -> List[AppareilRapproche]:
        self.type_categorie = self.config.type_de_categorie(self.categorie, self.types_outil)
        self.annoncees = list(dict.fromkeys(
            self._marque_outil(m) for m in self.l.marques_annoncees if m))
        table = {}
        for t in self.table_site:
            table.setdefault((cle_marque(t.marque), forme_normalisee(t.ref_modele)), t)
        vus_table: Set[tuple] = set()
        lignes: List[AppareilRapproche] = []
        for ligne in self.l.appareils:
            a = AppareilRapproche(ligne.numero, ligne.marque or '', ligne.ref_modele, ligne.nom,
                                  'description')
            a.suspecte = self._reference_suspecte(ligne.ref_modele)
            self._identifier_ligne(a, ligne.source_marque)
            cle = (cle_marque(a.marque), forme_normalisee(a.ref_modele))
            ligne_table = table.get(cle)
            if ligne_table is not None:
                a.provenance = 'les_deux'
                vus_table.add(cle)
            self._typer(a, ligne_table, ligne.type_ligne)
            lignes.append(a)
        # Union avec la table du site (§ 5.7) : lignes absentes de la description
        for cle, t in table.items():
            if cle in vus_table:
                continue
            a = AppareilRapproche(0, t.marque, t.ref_modele, t.nom, 'table')
            self._identifier_ligne(a, 'table')
            self._typer(a, t, '')
            lignes.append(a)
        self._decisions_distinct(lignes)
        self._doublons_par_le_nom(lignes)
        for a in lignes:
            # Marque que l'outil ne connaît pas (« PROFESSIONNELS HOTTE ») : une
            # création sous cette marque serait bancale (§ 10.14)
            a.marque_inconnue = bool(a.marque) and cle_marque(a.marque) not in self.marques_outil
            self._lier(a, principale)
            for categorie in a.doutes:
                self._doute(categorie, f"{a.marque or '?'} {a.ref_modele} : {a.raison}",
                            f"appareil:{a.numero}" if a.numero else f"table:{a.ref_modele}")
        self._ecarts(lignes)
        return lignes

    # --- Champs qui diffèrent d'un appareil connu ------------------------------
    @staticmethod
    def cible(a: AppareilRapproche) -> Optional[AppareilBase]:
        """Appareil de l'outil que la ligne désigne (retenu, proposé, ou seul candidat
        de même réf. sous une autre marque du groupe) ; None sinon."""
        ident = a.appareil_id if a.appareil_id is not None else a.proposition
        if ident is not None:
            return next((c for c in a.candidats if c.id == ident), None)
        if a.motif in ('meme_ref_groupe', 'nom_meme_ref'):
            memes = [c for c in a.candidats
                     if forme_normalisee(c.ref_modele) == forme_normalisee(a.ref_modele)]
            return memes[0] if len(memes) == 1 else None
        return None

    def _ecarts(self, lignes: List[AppareilRapproche]):
        """Type, marque (dans le groupe), écriture de la réf. et nom commercial d'un
        appareil connu qui diffèrent sur la fiche (rien n'est écrit sans choix, sauf
        un nom commercial vide dans l'outil, complété)."""
        cibles = {id(a): c for a in lignes if a.niveau != 'absent'
                  for c in [self.cible(a)] if c is not None}
        if not cibles:
            return
        ids = {c.id for c in cibles.values()}
        noms = self.acces.noms_commerciaux(ids) if any(a.nom for a in lignes) else {}
        tranches = self.acces.decisions_champs(ids) if self.memoires else {}
        for a in lignes:
            c = cibles.get(id(a))
            if c is None:
                continue
            ecarts = []
            if a.type_site and c.type and cle_marque(a.type_site) != cle_marque(c.type):
                ecarts.append(Ecart('type', c.type, a.type_site, c.id))
            if (a.marque and c.marque and cle_marque(a.marque) != cle_marque(c.marque)
                    and a.source_marque in ('entete', 'table')
                    and self.config.groupe_de.get(cle_marque(a.marque))
                    and self.config.groupe_de.get(cle_marque(a.marque))
                    == self.config.groupe_de.get(cle_marque(c.marque))):
                ecarts.append(Ecart('marque', c.marque, a.marque, c.id))
            if a.ref_modele and c.ref_modele != a.ref_modele \
                    and forme_normalisee(c.ref_modele) == forme_normalisee(a.ref_modele):
                ecarts.append(Ecart('ref', c.ref_modele, a.ref_modele, c.id))
            nom_outil = noms.get(c.id, '')
            if a.nom and _noms_differents(nom_outil, a.nom):
                ecarts.append(Ecart('nom', nom_outil, a.nom, c.id))
            for e in ecarts:
                e.tranche = bool(e.outil) and tranches.get((c.id, e.champ)) == e.site
            a.ecarts = ecarts

    def _reference_suspecte(self, ref: str) -> str:
        """Pourquoi une réf. lue ne ressemble pas à une réf. d'appareil ('' = normale) :
        elle n'est alors jamais créée en bloc (CDC § 5.2, création validée)."""
        ref = (ref or '').strip()
        if not any(c.isdigit() for c in ref):
            return "sans aucun chiffre"
        if any(c in ref for c in '():;'):
            return "parenthèses ou ponctuation inattendue"
        mots = ref.split()
        if len(mots) >= 3 and sum(any(c.isdigit() for c in m) for m in mots) >= 2:
            return "plusieurs codes sur une ligne"
        if len(mots) >= 2 and cle_marque(mots[0]) in self.marques_outil:
            return f"commence par une marque ({mots[0]})"
        return ''

    def _doublons_par_le_nom(self, lignes: List[AppareilRapproche]):
        """Ligne sans marque, absente, dont la « référence » est le nom commercial d'un
        appareil déjà cité par une autre ligne de la fiche — nom écrit sur la fiche, ou
        nom commercial de l'appareil dans l'outil (fiche 7164 : « WAT4564W » =
        Bauknecht 858341142074, cité plus haut par son 12NC) : rien à créer."""
        a_verifier = [a for a in lignes if a.niveau == 'absent' and not a.marque and not a.nom]
        if not a_verifier:
            return
        noms: Dict[str, AppareilRapproche] = {}
        for a in lignes:
            if a.nom and (a.niveau != 'absent' or a.marque):
                noms.setdefault(forme_normalisee(a.nom), a)
        identifies = {a.appareil_id: a for a in lignes if a.appareil_id is not None}
        for ident, nom in self.acces.noms_commerciaux(identifies).items():
            noms.setdefault(forme_normalisee(nom), identifies[ident])
        for a in a_verifier:
            autre = noms.get(forme_normalisee(a.ref_modele))
            if autre is not None and autre is not a:
                a.motif = 'doublon_nom'
                a.doutes = [d for d in a.doutes if d != 'marque_a_choisir']
                a.raison = (f"nom commercial de la ligne {autre.numero or 'table'} "
                            f"({autre.marque} {autre.ref_modele}) : déjà citée")

    def _marque_outil(self, marque: str) -> str:
        """Écriture de l'outil : clé exacte, alias de la configuration, puis singulier/pluriel."""
        cle = cle_marque(marque)
        if cle in self.marques_outil:
            return self.marques_outil[cle]
        alias = self.config.alias_marques.get(cle)
        if alias:
            return self.marques_outil.get(cle_marque(alias), alias)
        variante = cle[:-1] if cle.endswith('s') else cle + 's'
        return self.marques_outil.get(variante, marque)

    # --- Identification -------------------------------------------------------
    def _identifier_ligne(self, a: AppareilRapproche, source_marque: str):
        if a.marque_fiche:
            a.marque = self._marque_outil(a.marque_fiche)
            a.source_marque = source_marque or 'entete'
            niveau, candidats, raison = self._identifier(a.marque, a.ref_modele)
            self._appliquer(a, niveau, candidats, raison)
            if niveau == 'absent':
                self._chercher_ailleurs(a)
            return
        self._deduire_marque(a)

    def _identifier(self, marque: str, ref: str) -> Tuple[str, List[AppareilBase], str]:
        """Les deux passes du § 5.2 sur une marque."""
        candidats = self.acces.index_marque(marque).candidats(ref)
        if not candidats:
            return 'absent', [], "aucun candidat, ni exact ni normalisé"
        cle = cle_marque(marque)
        ecritures = list(dict.fromkeys(c.ref_modele for c in candidats))
        # Écritures déclarées distinctes de celle de la fiche : hors jeu
        distinctes = {e for e in ecritures if e != ref and self._decision(cle, ref, e) == 'distinct'}
        if distinctes:
            candidats = [c for c in candidats if c.ref_modele not in distinctes]
            ecritures = [e for e in ecritures if e not in distinctes]
            if not candidats:
                return 'absent', [], "écritures proches déclarées distinctes : création"
        if len(ecritures) > 1:
            memes = [e for e in ecritures if self._decision(cle, ref, e) == 'meme']
            if len(memes) == 1:
                candidats = [c for c in candidats if c.ref_modele == memes[0]]
                ecritures = memes
            else:
                return ('normalise_ambigu', candidats,
                        f"écritures en base : {' / '.join(ecritures)}")
        exacts = [c for c in candidats if c.ref_modele == ref]
        if exacts:
            if len(exacts) == 1:
                return 'exact', exacts, ''
            return 'exact_multiple', exacts, f"{len(exacts)} appareils {ref}"
        if len(candidats) == 1:
            return 'normalise', candidats, f"écriture de la base : {candidats[0].ref_modele}"
        return ('exact_multiple', candidats,
                f"{len(candidats)} appareils {candidats[0].ref_modele} (à la ponctuation près)")

    def _decision(self, cle_marque_: str, a: str, b: str) -> Optional[str]:
        return self.decisions.get((cle_marque_, frozenset((a, b))))

    @staticmethod
    def _appliquer(a: AppareilRapproche, niveau: str, candidats: List[AppareilBase], raison: str):
        a.niveau, a.candidats, a.raison = niveau, candidats, raison
        if niveau in ('exact', 'normalise'):
            a.appareil_id = candidats[0].id
        elif niveau == 'normalise_ambigu':
            exacts = [c for c in candidats if c.ref_modele == a.ref_modele]
            if len(exacts) == 1:
                a.proposition = exacts[0].id
            a.doutes.append('normalise_ambigu')
            a.motif = 'normalise_ambigu'
        elif niveau == 'exact_multiple':
            a.motif = 'exact_multiple'

    def _deduire_marque(self, a: AppareilRapproche):
        """Ligne sans en-tête : la marque se choisit parmi les marques annoncées."""
        if not self.annoncees:
            a.source_marque = 'a_choisir'
            a.niveau, a.raison = 'absent', "aucune marque annoncée"
            self._chercher_ailleurs(a)
            if 'marque_a_choisir' not in a.doutes:
                a.doutes.append('marque_a_choisir')
            if a.niveau == 'absent':
                a.motif = 'marque_a_choisir'
            return
        resultats = {m: self._identifier(m, a.ref_modele) for m in self.annoncees}
        for niveaux in (('exact', 'exact_multiple'), ('normalise', 'normalise_ambigu')):
            marques = [m for m, (n, _, _) in resultats.items() if n in niveaux]
            if len(marques) == 1:
                a.marque, a.source_marque = marques[0], 'deduite'
                niveau, candidats, raison = resultats[marques[0]]
                self._appliquer(a, niveau, candidats, raison)
                return
            if len(marques) > 1:
                a.source_marque = 'a_choisir'
                a.niveau = 'a_valider'
                a.candidats = [c for m in marques for c in resultats[m][1]]
                a.raison = f"trouvée sous {', '.join(marques)}"
                a.doutes.append('marque_a_choisir')
                a.motif = 'marque_a_choisir'
                return
        if len(self.annoncees) == 1:
            # Une seule marque annoncée (« GE » et « General Electric » ne font qu'une,
            # alias de la configuration) : c'est la marque de la ligne
            a.marque, a.source_marque = self.annoncees[0], 'annonce'
            a.niveau, a.raison = 'absent', f"absente sous {self.annoncees[0]}, seule marque annoncée"
            self._chercher_ailleurs(a)
            return
        a.source_marque = 'a_choisir'
        a.niveau, a.raison = 'absent', f"absente sous {', '.join(self.annoncees)}"
        self._chercher_ailleurs(a)
        if a.niveau == 'absent' and 'marque_a_choisir' not in a.doutes:
            a.doutes.append('marque_a_choisir')
            a.motif = 'marque_a_choisir'

    def _chercher_ailleurs(self, a: AppareilRapproche):
        """Absent sous sa marque : même réf. sous une marque du groupe, ou même nom commercial."""
        marques = ([a.marque] if a.marque else []) + self.annoncees
        groupe: List[str] = []
        for m in marques:
            groupe += [self._marque_outil(g) for g in self.config.marques_du_groupe(m)]
        voisines = {cle_marque(m) for m in groupe + marques}
        # Marques où la réf. a déjà été cherchée : celle de l'en-tête seule, ou toutes
        # les annoncées quand la marque était à déduire (une annoncée qui n'est pas
        # l'en-tête reste une marque du groupe où chercher : Ignis / Whirlpool)
        propres = ({cle_marque(a.marque)} if a.marque_fiche and a.marque
                   else {cle_marque(m) for m in marques})
        meme_ref = self.acces.appareils_par_ref([a.ref_modele]).get(a.ref_modele, [])
        ailleurs = [c for c in meme_ref
                    if cle_marque(c.marque) in voisines and cle_marque(c.marque) not in propres]
        if ailleurs:
            a.niveau, a.candidats = 'a_valider', ailleurs
            a.raison = f"réf. trouvée sous {', '.join(sorted({c.marque for c in ailleurs}))}"
            a.doutes.append('a_valider')
            a.motif = 'meme_ref_groupe'
            a.doutes = [d for d in a.doutes if d != 'marque_a_choisir']
            return
        # Même réf. exacte sous une marque hors du groupe : rien n'est lié, mais
        # la question « ces marques sont-elles du même groupe ? » se pose
        a.hors_groupe = sorted({c.marque for c in meme_ref
                                if cle_marque(c.marque) not in voisines and c.marque})
        if a.nom and marques:
            par_nom = self.acces.appareils_par_nom(list(dict.fromkeys(marques + groupe)), a.nom)
            if par_nom:
                a.niveau, a.candidats = 'a_valider', par_nom
                a.raison = (f"seulement par le nom commercial « {a.nom} » : "
                            f"{', '.join(sorted({c.ref_modele for c in par_nom}))}")
                a.doutes.append('a_valider')
                # Un seul candidat de même réf. (à la ponctuation près) : il est proposé
                memes = [c for c in par_nom
                         if forme_normalisee(c.ref_modele) == forme_normalisee(a.ref_modele)]
                if len(memes) == 1:
                    a.proposition = memes[0].id
                    a.motif = 'nom_meme_ref'
                elif len(par_nom) == 1:
                    a.motif = 'nom_ref_differente'
                else:
                    a.motif = 'nom_plusieurs'

    # --- Type (§ 5.6) ---------------------------------------------------------
    def _type_outil(self, t: str) -> str:
        return self.types_outil.get(cle_marque(t), t) if t else ''

    def _typer(self, a: AppareilRapproche, ligne_table: Optional[LigneTableSite], type_ligne: str):
        explicites = [(self._type_outil(ligne_table.type_appareil), 'table')
                      if ligne_table is not None and ligne_table.type_appareil else ('', ''),
                      (self._type_outil(type_ligne), 'ligne')]
        explicite = next(((t, s) for t, s in explicites if t), ('', ''))
        # Exact multiple : départage par le type (table, ligne, sinon catégorie)
        if a.niveau == 'exact_multiple':
            reference = explicite[0] or self.type_categorie
            retenus = [c for c in a.candidats if reference and cle_marque(c.type) == cle_marque(reference)]
            if len(retenus) == 1:
                a.appareil_id = retenus[0].id
                a.raison += f", départagé par le type {reference}"
            else:
                a.doutes.append('exact_multiple')
        if explicite[0]:
            a.type, a.source_type = explicite
            a.type_site = explicite[0]
            choisi = self._choisi(a)
            if choisi is not None and choisi.type and cle_marque(choisi.type) != cle_marque(a.type):
                # Même appareil, classé sous un autre type sur le site : il est relié
                # (même marque, même réf.) et le type de l'outil est gardé par défaut ;
                # l'écart est proposé à l'utilisateur (`ecarts`)
                a.type, a.source_type = choisi.type, 'base'
            return
        choisi = self._choisi(a)
        if choisi is not None and choisi.type:
            a.type, a.source_type = choisi.type, 'base'
            return
        types_base = {c.type for c in a.candidats if c.type}
        if choisi is None and len(types_base) > 1:
            a.doutes.append('type_ambigu')
            return
        if choisi is None and len(types_base) == 1:
            a.type, a.source_type = types_base.pop(), 'base'
            return
        if self.type_categorie:
            a.type, a.source_type = self.type_categorie, 'categorie'
            return
        a.doutes.append('type_manquant')

    @staticmethod
    def _choisi(a: AppareilRapproche) -> Optional[AppareilBase]:
        ident = a.appareil_id if a.appareil_id is not None else a.proposition
        return next((c for c in a.candidats if c.id == ident), None)

    def _decisions_distinct(self, lignes: List[AppareilRapproche]):
        multiples = [a for a in lignes if a.niveau == 'exact_multiple']
        if not multiples:
            return
        distinctes = self.acces.decisions_distinct({a.ref_modele for a in multiples})
        for a in multiples:
            if a.ref_modele in distinctes:
                a.raison += " (appareils déclarés distincts)"
            else:
                a.raison += " (doublon possible : aucune décision enregistrée)"

    # --- Lien (lignée) --------------------------------------------------------
    def _lier(self, a: AppareilRapproche, principale: Optional[str]):
        if a.niveau == 'absent':
            a.lien = 'nouveau'
            return
        ident = a.appareil_id if a.appareil_id is not None else a.proposition
        if ident is None:
            # Choix déjà fait à une lecture précédente : un seul des candidats est
            # lié à la pièce elle-même. Il est repris, sans redemander.
            lies = [c for c in a.candidats if principale in self.liens.get(c.id, set())]
            if len(lies) == 1:
                a.appareil_id, a.lien = lies[0].id, 'deja_lie'
                a.marque = a.marque or lies[0].marque
                a.type = a.type or lies[0].type
                a.raison += f" ; déjà lié à la pièce : {lies[0].marque} {lies[0].ref_modele}"
                a.doutes = [d for d in a.doutes if d not in _DOUTES_DE_CHOIX]
                a.motif = ''            # choix déjà fait : plus rien à demander
                return
            a.lien = ''
            return
        refs = self.liens.get(ident, set())
        if principale in refs:
            a.lien = 'deja_lie'
        elif refs:
            a.lien, a.couvert_par = 'deja_couvert', sorted(refs)
        else:
            a.lien = 'nouveau'
