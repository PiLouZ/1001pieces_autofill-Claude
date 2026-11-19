"""
Service Fiche produit complète

Bouton « Fiche complète » : assemble tout le code HTML de la fiche de la
référence recherchée selon un profil de l'onglet « Fiche » de la configuration
des exports, et le copie dans le presse-papiers.

- Titre : celui du bouton Titre (TitreProduitService.calculer_titre), avec le
  gabarit choisi dans le profil.
- Code produit : la référence tapée ; si elle est remplacée, la plus récente
  de sa lignée (comme le Titre). Pièce reprise du site : suivie de la 2ᵉ réf.
  du code produit de la fiche (paire Whirlpool / Indesit, CDC fiches site § 8.1).
- « Remplace les références » : toutes ses anciennes références (et celles de
  la 2ᵉ réf. du code produit).
- « Références équivalentes » : chaque équivalente hors lignée est suivie de
  ses propres anciennes références, de la plus fournie en appareils à la moins
  fournie. Une ligne par marque d'origine (puis par ligne mémorisée de la fiche
  du site) ; sans rien de mémorisé, une seule ligne. Les références écartées à
  la reprise n'apparaissent pas.
- Marques et appareils : ce qu'affiche le tableau (bandeaux et filtres de
  colonnes), comme les boutons HTML Marques / Détails.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.qt_imports import QApplication

from src.core.logger import app_logger
from src.services.html_export_service import HtmlExportService
from src.utils.fiche_produit_generator import FicheProduitGenerator


class FicheProduitService:
    """Génération et copie de la fiche produit complète."""

    def __init__(self, main_window):
        self.main_window = main_window
        self.generateur = FicheProduitGenerator()

    def generer_fiche(self, profile_name: Optional[str] = None) -> None:
        """Fiche de la recherche courante selon le profil demandé (défaut : profil par défaut)."""
        try:
            self._generer_fiche(profile_name)
        except Exception as e:
            app_logger.error(f"Fiche: génération échouée : {e}", exc_info=True)
            self.main_window.statusbar.showMessage(f"Fiche complète non générée : {e}", 8000)

    def _generer_fiche(self, profile_name: Optional[str]) -> None:
        contexte = self.contexte(relancer=lambda: self.generer_fiche(profile_name))
        if contexte:
            self.copier(contexte, profile_name)

    # ─── Contexte / rendu / copie (bouton et aperçu d'export) ───────────────

    def contexte(self, interactif: bool = True, relancer=None) -> Optional[Dict[str, Any]]:
        """Données de la fiche recherchée, préparées une fois pour toutes les variantes.
        relancer : rappelé une fois la référence choisie (recherche multi-références)."""
        seo = self.main_window.seo_service
        preparees = seo.preparer_donnees_fiche("fiche", "Référence pour la fiche complète",
                                               interactif=interactif, relancer=relancer)
        if not preparees:
            return None
        donnees, ref_obsolete = preparees
        reference = donnees['reference']

        appareils = self.main_window.export_manager.donnees_tableau()
        if not appareils:
            raison = "Aucun appareil affiché dans le tableau"
            if interactif:
                seo._signaler_refus("fiche", reference, raison)
            else:
                seo.raison_refus = raison
            return None

        refs = self.references_fiche(reference)
        return {'donnees': donnees, 'ref_obsolete': ref_obsolete, 'reference': reference,
                'appareils': appareils, 'remplace': refs['remplace'],
                'equivalentes': refs['equivalentes'], 'code_produit': refs['code_produit'],
                'lignes_equivalentes': refs['lignes_equivalentes'],
                'marques_html': HtmlExportService.generate_html_brands(appareils)}

    def rendre(self, contexte: Dict[str, Any], profile_name: Optional[str]) -> Dict[str, Any]:
        """Fiche selon la variante : {'html', 'resume', 'resultat', 'profil', 'strategie'}."""
        profil = self.main_window.export_config_service.get_fiche_profile(profile_name)
        resultat_titre, _ = self.main_window.titre_produit_service.calculer_titre(
            contexte['donnees'], profil.get('titre_profile') or None)
        details_profile = profil.get('details_profile') or None
        appareils = contexte['appareils']
        resultat = self.generateur.generer(
            profil, resultat_titre['titre'], contexte['marques_html'],
            contexte['reference'], contexte['remplace'], contexte['equivalentes'],
            lambda reste: HtmlExportService.generate_html_details(
                appareils, profile_name=details_profile, char_limit=reste),
            code_produit=contexte.get('code_produit'),
            lignes_equivalentes=contexte.get('lignes_equivalentes'),
        )
        strategie = HtmlExportService.last_strategy_used
        resume = f"{resultat['longueur']} car."
        if resultat['limite']:
            resume += f" / {resultat['limite']}"
        resume += f" · {self._resume_appareils(appareils)}"
        reduction = self._reduction(resultat['html'], strategie)
        if reduction:
            resume += f" · {reduction}"
        return {'html': resultat['html'], 'resume': resume, 'resultat': resultat,
                'profil': profil, 'strategie': strategie}

    def copier(self, contexte: Dict[str, Any], profile_name: Optional[str]) -> None:
        """Copier la fiche et la signaler (barre d'état + historique)."""
        rendu = self.rendre(contexte, profile_name)
        QApplication.clipboard().setText(rendu['html'])
        self._signaler(rendu['profil'], contexte['donnees'], contexte['ref_obsolete'],
                       contexte['appareils'], contexte['remplace'], contexte['equivalentes'],
                       rendu['resultat'], rendu['strategie'],
                       code_produit=contexte.get('code_produit'),
                       lignes_equivalentes=contexte.get('lignes_equivalentes'))

    # ─── Références liées ────────────────────────────────────────────────────

    def references_liees(self, reference: str) -> Tuple[List[str], List[List[str]]]:
        """
        (anciennes références de `reference`, lignées équivalentes).

        Une lignée équivalente = [équivalente, ses anciennes références…] ; une
        ancienne version dont la remplaçante est hors du groupe a donc sa propre
        lignée. Lignées classées par nombre d'appareils décroissant ; à égalité,
        celles qui commencent par une lettre d'abord, puis par ordre alphabétique.
        Chaque référence n'apparaît qu'une fois.
        """
        db = self.main_window.db_manager
        try:
            remplace = list(db.get_all_predecessors(reference))
            hors_chaine = list(db.get_equivalents_hors_chaine(reference))
        except Exception as e:
            app_logger.warning(f"Fiche: références liées de {reference} illisibles : {e}")
            return [], []

        deja = {reference, *remplace}
        lignees = []
        for equivalente in hors_chaine:
            if equivalente in deja:
                continue
            try:
                anciennes = db.get_all_predecessors(equivalente)
            except Exception as exc:
                app_logger.warning(f"Anciennes réf. de l'équivalente {equivalente} non lues : {exc}")
                anciennes = []
            lignee = [equivalente] + [r for r in anciennes if r not in deja and r != equivalente]
            deja.update(lignee)
            lignees.append(lignee)

        # Même décompte que les métas (appareils distincts de toute la lignée)
        seo = self.main_window.seo_service
        nb = {lignee[0]: seo._count_compatible_models(lignee) for lignee in lignees}
        lignees.sort(key=lambda l: (-nb[l[0]], l[0][:1].isdigit(), l[0]))
        return remplace, lignees

    def references_fiche(self, reference: str) -> Dict[str, Any]:
        """
        Références des lignes de la fiche :
        {'code_produit', 'remplace', 'equivalentes' (lignées), 'lignes_equivalentes'}.

        Mémoire de la reprise des fiches du site (CDC § 5.3, § 8.1) :
        - une équivalente mémorisée comme 2ᵉ réf. du code produit (ligne 0)
          d'une pièce vendue sur le site rejoint le code produit ; ses anciennes
          références rejoignent « Remplace » ;
        - la référence associée Whirlpool / Indesit / Beko retenue à l'import
          (§ 10.17) rejoint aussi le code produit ; la référence **principale**
          vient toujours en premier, quelle que soit la référence recherchée ;
        - les autres lignées sont regroupées par marque d'origine, puis par
          ligne mémorisée (`lignes_par_origine`) ;
        - les références écartées à la reprise disparaissent du code produit et
          des équivalentes, pas de « Remplace » (écartée = pas une équivalente) ;
        - « Remplace » suit l'ordre de la ligne de la fiche (`rang_fiche`), les
          références sans position mémorisée à la suite, dans l'ordre actuel ;
        - chaque paire de réf. associées (Whirlpool / Indesit / Beko) se suit sur
          la même ligne : la jumelle d'une ancienne référence rejoint « Remplace »
          juste derrière elle (`jumelles_a_la_suite`).
        Sans mémoire (pièce saisie dans l'outil, base non migrée) : comme avant,
        une seule ligne d'équivalentes et la seule référence en code produit.
        """
        remplace, lignees = self.references_liees(reference)
        db = self.main_window.db_manager
        try:
            memoire = db.memoire_equivalences(reference)
            principales = db.pieces_avec_produit_site([reference] + [l[0] for l in lignees])
            ecartees = db.references_ecartees(
                [reference, *remplace, *(r for l in lignees for r in l)])
            rangs = db.rangs_remplace([*remplace, *(r for l in lignees for r in l[1:])])
        except Exception as e:
            # Base sans les tables de la reprise, ou fenêtre de test sans ces lectures
            app_logger.debug(f"Fiche: mémoire de la reprise de {reference} non lue : {e}")
            memoire, principales, ecartees, rangs = {}, set(), set(), {}
        try:
            associees = db.references_associees_de(reference)
            principale = db.reference_principale_de(reference)
        except Exception as e:
            app_logger.debug(f"Fiche: références associées de {reference} non lues : {e}")
            associees, principale = set(), None

        ligne_0 = {l[0] for l in lignees
                   if reference in principales and l[0] not in principales
                   and (memoire.get(l[0]) or (None, None))[1] == 0}
        ligne_0 -= self.jumelles_hors_du_code(
            ligne_0, {reference, principale, *associees, *ligne_0})

        code, autres = [reference], []
        remplace = list(remplace)
        for lignee in lignees:
            tete = lignee[0]
            if tete in associees or tete in ligne_0:
                code.append(tete)
                remplace += [r for r in lignee[1:] if r not in remplace]
            else:
                autres.append(lignee)

        def garder(refs):
            return [r for r in refs if r not in ecartees]
        autres = [l for l in (garder(l) for l in autres) if l]
        lignes = [l for l in (garder(l) for l in self.lignes_par_origine(autres, memoire)) if l]
        remplace = self.ordre_de_la_fiche(remplace, rangs)
        try:
            paires = db.paires_associees_parmi(
                [*remplace, *(r for l in lignes for r in l)])
        except Exception as e:
            app_logger.debug(f"Fiche: paires de réf. associées de {reference} non lues : {e}")
            paires = []
        if paires:
            remplace, *lignes = self.jumelles_a_la_suite([remplace, *lignes], paires)
            lignes = [l for l in lignes if l]
            dans_remplace = set(remplace)
            autres = [l for l in ([r for r in l if r not in dans_remplace] for l in autres) if l]
        if principale and principale in code[1:]:
            # Ordre fixe : la principale d'abord, puis la référence recherchée
            code = [principale] + [r for r in code if r != principale]
        # « Remplace » non filtré : une réf. écartée l'est comme équivalente (§ 5.3) ;
        # si elle est dans la chaîne de remplacements, elle garde sa place ici
        return {'code_produit': [code[0]] + garder(code[1:]), 'remplace': remplace,
                'equivalentes': autres, 'lignes_equivalentes': lignes}

    def jumelles_hors_du_code(self, candidates: Set[str], du_code: Set[str]) -> Set[str]:
        """Parmi les équivalentes `candidates` marquées « ligne 0 », celles dont la
        réf. associée n'est pas du code produit (`du_code`) : elles restent avec
        leur jumelle dans les équivalentes, au lieu de monter seules dans le code
        produit (garde-fou contre une marque « ligne 0 » erronée)."""
        if not candidates:
            return set()
        db = self.main_window.db_manager
        hors = set()
        try:
            for ref in candidates:
                jumelles = db.references_associees_de(ref)
                if jumelles and not jumelles & du_code:
                    hors.add(ref)
        except Exception as e:
            app_logger.debug(f"Fiche: jumelles des équivalentes de ligne 0 non lues : {e}")
        return hors

    @staticmethod
    def ordre_de_la_fiche(refs: List[str], rangs: Dict[str, int]) -> List[str]:
        """« Remplace » dans l'ordre de la fiche du site (position mémorisée à la
        reprise), puis les références sans position dans l'ordre actuel (chaîne
        de la pièce, puis de ses équivalentes du code produit)."""
        if not rangs:
            return refs
        avec = sorted((r for r in refs if r in rangs), key=lambda r: rangs[r])
        return avec + [r for r in refs if r not in rangs]

    @staticmethod
    def jumelles_a_la_suite(lignes: List[List[str]],
                            paires: List[Tuple[str, str]]) -> List[List[str]]:
        """Chaque paire (principale, associée) à la suite, sur la même ligne :
        celle des deux qui vient la première (« Remplace » avant les équivalentes,
        puis à gauche) garde sa place, l'autre se range juste derrière. Une paire
        déjà côte à côte garde son ordre (celui de la fiche du site). Une référence
        absente des lignes, ou déjà rangée avec une autre jumelle, laisse la paire
        telle quelle. Lignes vidées gardées (vides)."""
        lignes = [list(l) for l in lignes]
        rangees = set()
        for principale, associee in paires:
            if principale in rangees or associee in rangees:
                continue
            places = {}
            for n, ligne in enumerate(lignes):
                for i, ref in enumerate(ligne):
                    if ref in (principale, associee) and ref not in places:
                        places[ref] = (n, i)
            if len(places) < 2:
                continue
            rangees.update((principale, associee))
            n, i = min(places.values())
            if sorted(places.values()) == [(n, i), (n, i + 1)]:
                continue                        # déjà à la suite
            tete = lignes[n][i]
            paire = [tete, associee if tete == principale else principale]
            avant = [r for r in lignes[n][:i] if r not in paire]
            apres = [r for r in lignes[n][i:] if r not in paire]
            for m in range(len(lignes)):
                if m != n:
                    lignes[m] = [r for r in lignes[m] if r not in paire]
            lignes[n] = avant + paire + apres
        return lignes

    @staticmethod
    def lignes_par_origine(lignees: List[List[str]],
                           memoire: Dict[str, Tuple[Optional[str], Optional[int]]]
                           ) -> List[List[str]]:
        """Une ligne par marque d'origine, puis par ligne mémorisée de la fiche ;
        les lignées sans rien de mémorisé ensemble. Chaque lignée suit sa tête.
        Lignes rangées par n° de ligne de la fiche ; sans n°, à la suite, dans
        l'ordre des lignées (le plus d'appareils d'abord)."""
        lignes: Dict[Tuple[str, Any], List[str]] = {}
        rang: Dict[Tuple[str, Any], float] = {}
        for lignee in lignees:
            origine, ligne = memoire.get(lignee[0]) or (None, None)
            if origine:
                cle = ('origine', origine.strip().casefold())
            elif ligne:
                cle = ('ligne', ligne)
            else:
                cle = ('', None)
            lignes.setdefault(cle, []).extend(lignee)
            rang[cle] = min(rang.get(cle, float('inf')), ligne if ligne else float('inf'))
        apparition = {c: i for i, c in enumerate(lignes)}
        return [lignes[c] for c in sorted(lignes, key=lambda c: (rang[c], apparition[c]))]

    # ─── Compte rendu ────────────────────────────────────────────────────────

    @staticmethod
    def _resume_appareils(appareils) -> str:
        nb_marques = len({r[1].strip() for r in appareils if len(r) > 1 and r[1] and r[1].strip()})
        return (f"{len(appareils)} appareil{'s' if len(appareils) > 1 else ''}, "
                f"{nb_marques} marque{'s' if nb_marques > 1 else ''}")

    @staticmethod
    def _reduction(fiche_html: str, strategie: str) -> str:
        """Réduction appliquée à la liste des appareils pour tenir dans la limite ('' sinon)."""
        if "Données trop volumineuses" in fiche_html:
            return "limite dépassée : liste des appareils remplacée par un avertissement"
        if strategie == 'ref_modele':
            return "limite atteinte : références modèle uniquement"
        if strategie == 'commercial_ref':
            return "limite atteinte : références commerciales uniquement"
        return ""

    def _signaler(self, profil, donnees, ref_obsolete, appareils, remplace, equivalentes,
                  resultat, strategie, code_produit=None, lignes_equivalentes=None) -> None:
        reference = donnees['reference']
        resume = self._resume_appareils(appareils)
        status = f"Fiche copiée ({resultat['longueur']} car., {resume})"
        if ref_obsolete:
            status += f" [Supersédée → {reference}]"

        detail = f"Fiche: '{reference}'"
        if ref_obsolete:
            detail += f" (remplace {ref_obsolete})"
        detail += f" — profil « {profil.get('name', '')} »"
        detail += f"\n==> {resume} ; {resultat['longueur']} car."
        if code_produit and len(code_produit) > 1:
            detail += f"\n==> Code produit : {' '.join(code_produit)}"
        if remplace:
            detail += f"\n==> Remplace : {' '.join(remplace)}"
        if lignes_equivalentes is not None:
            for ligne in lignes_equivalentes:
                detail += f"\n==> Équivalentes : {' '.join(ligne)}"
        elif equivalentes:
            detail += f"\n==> Équivalentes : {' '.join(r for lignee in equivalentes for r in lignee)}"
        reduction = self._reduction(resultat['html'], strategie)
        if reduction:
            detail += f"\n==> {'[!] ' if 'dépassée' in reduction else ''}{reduction[0].upper()}{reduction[1:]}"

        self.main_window.user_interaction_service.add_to_history(detail)
        self.main_window.statusbar.showMessage(status, 4000)
