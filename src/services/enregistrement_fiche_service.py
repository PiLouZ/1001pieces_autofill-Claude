"""
Enregistrement d'une fiche du site après validation de l'aperçu
(CDC docs/cdc_import_fiches_site.md, § 7.5, étape 3)

Une fiche du site est un import comme les autres (§ 10.12) : son
`PlanEnregistrement` (src/utils/rapprochement_fiche/decisions.py) devient un fichier
d'import (`FileType.FICHE_SITE`, une ligne par appareil, déjà identifiée par la
marque et la réf.) que `ImportManager._run_import_files` écrit comme un PDF ou un
CSV : orthographe alignée, auto-complétion du type et de la marque, appareils
créés, liens, suggestions à valider, auto-complétés à vérifier. Un lot de fiches
est un import de plusieurs fichiers.

Ce qui est propre à la reprise s'écrit dans le crochet `apres_ecriture` de
l'import, fiche par fiche : provenance des liens, remplacements et équivalences
(`import_relations.apply_relations`), marques d'origine, ordre des « Remplace »,
produit du site, décisions consignées. La pièce (fantôme → réelle, libellé) est
posée avant l'import, pour que les relations propagent son libellé.

Ajout seul (§ 6.2) : rien n'est supprimé. Relire une fiche ne crée aucun
doublon : un appareil créé ressort « exact » à la relecture, un lien présent ne
fait que compléter sa provenance, une équivalence présente est ignorée.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..core.logger import app_logger
from ..utils.rapprochement_fiche.decisions import PlanEnregistrement

_ENTETES_HTTP = {'User-Agent': 'Mozilla/5.0 (compatible; lecteur de fiches)'}
_DELAI_HTTP = 20


def telecharger_page(url: str) -> str:
    """Page publique d'une fiche (appelé hors du thread principal par l'aperçu)."""
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen
    from ..utils.certificats import contexte_ssl
    if urlparse(url).scheme not in ('http', 'https'):
        raise ValueError("le lien doit commencer par http:// ou https://")
    with urlopen(Request(url, headers=_ENTETES_HTTP), timeout=_DELAI_HTTP,
                 context=contexte_ssl()) as reponse:
        jeu = reponse.headers.get_content_charset() or 'utf-8'
        return reponse.read().decode(jeu, errors='replace')
from .base_service import BaseService
from .import_relations import CardData, Group, KIND_EQUIVALENCE, apply_relations


def lien_produit(id_product) -> str:
    """Page du produit sur 1001pieces.com, d'après son n° (PrestaShop)."""
    return f"https://www.1001pieces.com/index.php?controller=product&id_product={id_product}"


def cle_identite_creation(a) -> str:
    """Clé d'identité d'un appareil à créer, pour l'import : même marque et même
    forme normalisée = un seul appareil, partagé par les lignes et les fiches
    (règle du § 5.2, celle de `cle_creation` du lot)."""
    from ..utils.lecteur_fiche.lecteur import cle_marque
    from ..utils.rapprochement_fiche.acces_base import forme_normalisee
    return f"fiche:{cle_marque(a.marque)}|{forme_normalisee(a.ref_modele)}"


def lignes_import(plan: PlanEnregistrement) -> List[Dict[str, object]]:
    """Lignes du fichier d'import d'une fiche : un appareil reconnu (son id), ou à
    créer (marque, réf., nom, type, et sa clé d'identité). Un appareil cité par
    plusieurs lignes n'y figure qu'une fois (sa provenance réunie est écrite après)."""
    from ..core.import_manager import ImportManager
    creations = {a.index: a for a in plan.appareils_a_creer}
    lignes, vus = [], set()
    for cible, _provenance in plan.liens:
        if isinstance(cible, tuple):
            a = creations.get(cible[1])
            if a is None:
                continue
            cle = cle_identite_creation(a)
            ligne = {'type': a.type, 'manufacturer': a.marque, 'ref_modele': a.ref_modele,
                     'commercial_ref': a.nom, ImportManager.CLE_IDENTITE: cle}
        else:
            cle = f"id:{cible}"
            ligne = {ImportManager.CLE_APPAREIL: cible, ImportManager.CLE_IDENTITE: cle}
        if cle not in vus:
            vus.add(cle)
            lignes.append(ligne)
    return lignes


@dataclass
class ResultatEnregistrement:
    ok: bool = True
    piece: str = ''                     # 'creee', 'promue', 'existante'
    appareils_crees: int = 0
    liens_crees: int = 0
    liens_completes: int = 0
    liens_inchanges: int = 0
    relations: Dict[str, int] = field(default_factory=dict)
    journal: List[str] = field(default_factory=list)
    erreur: str = ''
    # Champs d'appareils connus pris sur le site (id → {colonne: valeur}) : écrits
    # après coup, sur le thread principal, par la sauvegarde événementielle
    maj_appareils: Dict[int, Dict[str, str]] = field(default_factory=dict)
    champs_modifies: int = 0
    non_importees: List[str] = field(default_factory=list)
    # Résultats de l'import (même forme qu'un import PDF/CSV : historique,
    # suggestions à valider, auto-complétés à vérifier)
    resultats_import: Dict[str, object] = field(default_factory=dict)

    def resume(self) -> str:
        r = self.relations
        return (f"pièce {self.piece} ; {self.appareils_crees} appareil(s) créé(s) ; "
                f"{self.liens_crees} lien(s) créé(s), {self.liens_completes} complété(s) ; "
                f"{r.get('successions', 0)} remplacement(s), {r.get('equivalences', 0)} "
                f"équivalence(s)" + (f", {r['errors']} refus" if r.get('errors') else ''))


class EnregistrementFicheService(BaseService):
    """Écrit une fiche validée dans l'outil."""

    def __init__(self, db_manager, parent_window=None, parent=None, configuration=None):
        super().__init__(parent_window, parent)
        self.db = db_manager
        self._configuration = configuration

    # -------------------------------------------------------------------------
    # Lecture et rapprochement (rien n'est écrit)
    # -------------------------------------------------------------------------
    def configuration(self):
        if self._configuration is None:
            from ..utils.rapprochement_fiche import charger_configuration
            self._configuration = charger_configuration()
        # Appellations de l'onglet Appareils (coupe du titre en libellé), lues à
        # chaque fois : un changement de l'onglet vaut dès la fiche suivante
        service = getattr(self.parent_window, 'export_config_service', None)
        if service is not None:
            try:
                self._configuration.appellations_appareils = \
                    service.get_config().get('synonymes_appareils')
            except Exception as e:
                app_logger.debug(f"Appellations des appareils non lues : {e}")
        return self._configuration

    def _modeles(self):
        import copy
        from ..utils.lecteur_fiche import modeles_depuis_config
        service = getattr(self.parent_window, 'export_config_service', None)
        if service is not None:
            config = service.get_config()
        else:
            from .export_config_service import DEFAULT_CONFIG
            config = copy.deepcopy(DEFAULT_CONFIG)
        return modeles_depuis_config(config)

    def analyser_page(self, page_html: str, url: str = ''):
        """(PagePublique, Rapprochement) d'une page publique de fiche."""
        from ..utils.lecteur_fiche import lire_page_publique
        from ..utils.rapprochement_fiche import AccesBaseLecture, rapprocher
        with self.db._query_lock:
            acces = AccesBaseLecture(self.db.conn)
            page = lire_page_publique(page_html, url=url, modeles=self._modeles(),
                                      marques_connues=list(acces.marques().values()),
                                      types_connus=list(acces.types().values()))
            r = rapprocher(page.description, acces, self.configuration(), page=page,
                           memoires=True)
        return page, r

    def analyser_description(self, texte: str):
        """(LectureFiche, Rapprochement) d'une description collée (HTML ou texte)."""
        from ..utils.lecteur_fiche import lire_description
        from ..utils.rapprochement_fiche import AccesBaseLecture, rapprocher
        with self.db._query_lock:
            acces = AccesBaseLecture(self.db.conn)
            lecture = lire_description(texte, modeles=self._modeles(),
                                       marques_connues=list(acces.marques().values()),
                                       types_connus=list(acces.types().values()))
            r = rapprocher(lecture, acces, self.configuration(), memoires=True)
        return lecture, r

    def types_outil(self) -> List[str]:
        from ..utils.rapprochement_fiche import AccesBaseLecture
        with self.db._query_lock:
            return sorted(AccesBaseLecture(self.db.conn).types().values(), key=str.lower)

    def marques_outil(self) -> List[str]:
        from ..utils.rapprochement_fiche import AccesBaseLecture
        with self.db._query_lock:
            return sorted(AccesBaseLecture(self.db.conn).marques().values(), key=str.lower)

    # -------------------------------------------------------------------------
    # Enregistrement
    # -------------------------------------------------------------------------

    def planifier_par_regles(self, r) -> PlanEnregistrement:
        """Plan d'une fiche par les règles de l'import, sans question (§ 10.12)."""
        from ..utils.rapprochement_fiche.regles_import import planifier_import
        return planifier_import(r, appellations=self.configuration().appellations_appareils)

    def enregistrer(self, plan: PlanEnregistrement) -> ResultatEnregistrement:
        if not plan.pret:
            res = ResultatEnregistrement(ok=False)
            res.erreur = "fiche non prête : " + "; ".join(plan.a_completer or ["pièce introuvable"])
            return res
        try:
            res = self.ecrire_par_import([plan])[0]
        except Exception as e:      # le plan reste rejouable : tout y est idempotent
            app_logger.error(f"[Fiche site] Enregistrement de {plan.ref_piece} interrompu : {e}")
            res = ResultatEnregistrement(ok=False, erreur=str(e))
        self._apres_ecriture(res)
        app_logger.info(f"[Fiche site] {plan.ref_piece} : {res.resume()}")
        return res

    # -------------------------------------------------------------------------
    def ecrire_par_import(self, plans: List[PlanEnregistrement], noms: Optional[List[str]] = None,
                          progression=None, annule=None) -> List[ResultatEnregistrement]:
        """Écrit des fiches par l'import (une fiche = un fichier). Retourne un résultat
        par fiche ; `resultats_import` (le même pour toutes) est celui de l'import.
        Une fiche que l'import n'a pas traitée (annulation, erreur) a `ok` faux, rien
        de propre à la reprise n'est écrit pour elle. Hors du thread principal."""
        from ..core.import_manager import ImportManager
        config, resultats = self.configuration_import(plans, noms)
        results = ImportManager(self.db)._run_import_files(config, progress_cb=progression,
                                                            cancel_check=annule)
        for res in resultats:
            res.resultats_import = results
        return resultats

    def configuration_import(self, plans: List[PlanEnregistrement],
                             noms: Optional[List[str]] = None):
        """(ImportConfiguration, résultats par fiche) : les pièces sont posées, l'import
        reste à lancer (`_run_import_files`, ou l'import réel de la fenêtre d'import).
        Les résultats se remplissent dans le crochet `apres_ecriture`."""
        from ..core.import_manager import (FileType, ImportConfiguration, ImportFile,
                                           ImportType)
        db = self.db
        resultats = [ResultatEnregistrement(non_importees=list(p.non_importees)) for p in plans]
        # 1. Pièces avant l'import : fantôme → réelle, libellé (propagé par les relations)
        pieces = []
        with db._query_lock:
            for p, res in zip(plans, resultats):
                piece_id, res.piece = db._creer_ou_promouvoir_piece(
                    p.ref_piece, p.libelle, p.remplacer_libelle)
                pieces.append(piece_id)
            db.conn.commit()

        # 2. Un fichier d'import par fiche (chemin unique : deux fiches peuvent citer
        # la même pièce, par exemple une pièce d'origine et un générique)
        fichiers = []
        for k, p in enumerate(plans):
            nom = noms[k] if noms else f"fiche {p.ref_piece}"
            fichiers.append(ImportFile(path=f"{nom} #{k + 1}" if len(plans) > 1 else nom,
                                       type=FileType.FICHE_SITE, suggested_reference=p.ref_piece,
                                       data=lignes_import(p)))

        def apres_ecriture(im, results):
            # 3. Propre à la reprise, fiche par fiche, pour les fichiers traités
            for k, (p, res) in enumerate(zip(plans, resultats)):
                traite = im._resultats_par_fichier.get(fichiers[k].path)
                if traite is None:
                    res.ok, res.erreur = False, "fiche non importée (annulation ou erreur)"
                    continue
                nouveaux = {}
                for a in p.appareils_a_creer:
                    # Créé par cette fiche ou par une précédente du même import
                    ident = im._ids_session.get(cle_identite_creation(a))
                    if ident is not None:
                        nouveaux[a.index] = ident
                res.appareils_crees = traite.get('new_entries', 0)
                self._ecrire_suite(p, res, pieces[k], nouveaux,
                                   liens_import=traite.get('associations_created', 0))
                if p.a_refaire is not None:
                    self._noter_a_refaire(p)
                    results.setdefault('fiches_a_refaire', []).append(
                        (p.ref_piece, p.a_refaire.raison))

            for res in resultats:
                res.resultats_import = results

        config = ImportConfiguration(
            files=fichiers,
            import_type=ImportType.SINGLE_FILE if len(fichiers) == 1 else ImportType.MULTI_FILE,
            individual_references={f.path: p.ref_piece for f, p in zip(fichiers, plans)},
            apres_ecriture=apres_ecriture)
        return config, resultats

    # -------------------------------------------------------------------------
    # Fiche seule dans la fenêtre d'import (§ 10.12, PR 2)
    # -------------------------------------------------------------------------
    def fiche_a_importer(self, r, url: str = '') -> 'FicheAImporter':
        """Fiche lue, planifiée par les règles de l'import, prête pour la fenêtre d'import."""
        return FicheAImporter(r, self.planifier_par_regles(r), url)

    def preparer_import(self, fiche: 'FicheAImporter', saisie) -> Tuple[object, ResultatEnregistrement]:
        """La fenêtre d'import est validée : ses saisies (réf., libellé, Succession,
        Obsolète) reviennent dans le plan, puis la configuration de l'import réel est
        faite. Retourne (configuration, résultat de la fiche). Thread principal."""
        plan = fiche.appliquer_saisie(saisie)
        config, resultats = self.configuration_import([plan], noms=[fiche.nom_fichier])
        config.obsolete_refs = list(saisie.obsolete_refs or [])
        return config, resultats[0]

    def apres_import(self, res: ResultatEnregistrement):
        """Fin de l'import réel d'une fiche (thread principal) : noms commerciaux vides
        complétés, caches. La fenêtre principale fait le reste comme après tout import."""
        if res.maj_appareils:
            res.champs_modifies = self.ecrire_champs_appareils(res.maj_appareils)
        try:
            self.db.invalidate_search_cache(invalidate_total_count=True)
        except Exception as e:
            app_logger.warning(f"[Fiche site] cache de recherche non invalidé : {e}")

    def _noter_a_refaire(self, plan: PlanEnregistrement):
        """Fiche aux créations retenues : notée « à refaire depuis les PDF » (§ 10.14)."""
        id_product = (plan.produit or {}).get('id_product')
        with self.db._query_lock:
            self.db._noter_fiche_a_refaire(plan.ref_piece, id_product, plan.a_refaire,
                                           self._maintenant())
            self.db.conn.commit()

    def _ecrire_suite(self, plan: PlanEnregistrement, res: ResultatEnregistrement,
                      piece_id: int, nouveaux: Dict[int, int], liens_import: int = 0):
        """Propre à la reprise, après l'import de la fiche. `liens_import` : liens que
        l'import vient de créer (sans provenance) ; la provenance les complète."""
        db = self.db
        # 3. Provenance des liens (§ 5.7)
        liens = []
        for cible, provenance in plan.liens:
            ident = nouveaux.get(cible[1]) if isinstance(cible, tuple) else cible
            if ident is not None:
                liens.append((ident, provenance))
        with db._query_lock:
            compte = db._ajouter_liens_provenance(piece_id, liens)
            db.conn.commit()
        res.liens_crees = liens_import + compte['crees']
        res.liens_completes = max(0, compte['completes'] - liens_import)
        res.liens_inchanges = compte['inchanges']

        # 4. Remplacements et équivalences : tronc des relations d'import
        cartes = [CardData(ref=a, replaced_by=n) for a, n in plan.remplacements]
        groupes = ([Group(kind=KIND_EQUIVALENCE, courante=plan.ref_piece,
                          members=list(plan.equivalences))] if plan.equivalences else [])
        res.relations = apply_relations(groupes, cartes, db, journal=res.journal)

        # 5. Étiquettes d'origine, produit du site, décisions consignées
        with db._query_lock:
            db._definir_origines(plan.origines)
            db._definir_rangs_remplace(plan.rangs_remplace)
            produit = plan.produit
            if produit:
                precedente = produit.get('ref_interne_precedente')
                if precedente:      # réf. interne changée sur le site : le site fait foi
                    db.cursor.execute("DELETE FROM produits_site WHERE ref_interne = ?",
                                      [precedente])
                db._enregistrer_produit_site(produit['ref_interne'], produit['id_product'],
                                             produit['ref_piece'], produit['ean'], produit['lu_le'])
            le = produit['lu_le'] if produit else None
            db._enregistrer_decisions_ecritures(plan.decisions_ecritures, le)
            db._enregistrer_decisions_references(plan.decisions_references, le)
            db.conn.commit()
        for ident, colonnes in plan.maj_appareils.items():
            res.maj_appareils.setdefault(ident, {}).update(colonnes)

    @staticmethod
    def _maintenant() -> str:
        from datetime import datetime
        return datetime.now().isoformat(timespec='seconds')

    def ecrire_champs_appareils(self, maj: Dict[int, Dict[str, str]]) -> int:
        """Champs d'appareils connus pris sur le site (type, marque, écriture de la
        réf., nom commercial), écrits par la sauvegarde événementielle (thread
        principal). Sans fenêtre (scripts, tests) : la même mise à jour par lots
        du gestionnaire de base, que la sauvegarde événementielle appelle."""
        maj = {i: dict(c) for i, c in maj.items() if c}
        if not maj:
            return 0
        sauvegarde = getattr(self.parent_window, 'event_driven_save_service', None)
        if sauvegarde is not None and hasattr(sauvegarde, 'enregistrer_champs_appareils'):
            ok = sauvegarde.enregistrer_champs_appareils(maj)
        else:
            ok = self.db.update_multiple_cells_batch(maj)
        n = sum(len(c) for c in maj.values())
        if ok:
            app_logger.info(f"[Fiche site] {n} champ(s) d'appareils pris sur le site "
                            f"({len(maj)} appareil(s))")
        else:
            app_logger.error(f"[Fiche site] {n} champ(s) d'appareils non écrits")
        return n if ok else 0

    def _apres_ecriture(self, res: ResultatEnregistrement, source: str = "fiche_site"):
        """Caches invalidés comme après un import, puis sauvegarde événementielle
        (thread principal : la sauvegarde passe par des minuteries Qt)."""
        if res.maj_appareils:
            res.champs_modifies = self.ecrire_champs_appareils(res.maj_appareils)
        bilan = {'new_entries': res.appareils_crees,
                 'associations_created': res.liens_crees + res.liens_completes}
        try:
            self.db.invalidate_search_cache(invalidate_total_count=True)
        except Exception as e:
            app_logger.warning(f"[Fiche site] cache de recherche non invalidé : {e}")
        invalidation = getattr(self.db, 'cache_invalidation', None)
        if invalidation is not None:
            invalidation.invalidate_after_import(bilan)
        sauvegarde = getattr(self.parent_window, 'event_driven_save_service', None)
        if sauvegarde is not None:
            sauvegarde.save_after_import(source)
        self.signaler_import(res.resultats_import)

    def signaler_import(self, resultats_import) -> None:
        """Comme après un import PDF/CSV : récapitulatif dans l'historique, boutons
        « Suggestions à valider » et « Auto-complétés à vérifier » (thread principal)."""
        fin = getattr(self.parent_window, '_on_import_complete', None)
        if resultats_import and callable(fin):
            try:
                fin(resultats_import)
            except Exception as e:
                app_logger.warning(f"[Fiche site] récapitulatif d'import non affiché : {e}")


# =============================================================================
# Fiche à importer (fenêtre d'import)
# =============================================================================

@dataclass
class FicheAImporter:
    """Une fiche du site lue et planifiée, portée par son fichier d'import
    (`ImportFile.fiche`) jusqu'à la validation de la fenêtre d'import."""
    rapprochement: object
    plan: PlanEnregistrement
    url: str = ''
    nom_produit: str = ''         # nom du produit dans l'export (secours du titre)

    @property
    def lien_site(self) -> str:
        """Page de la fiche sur le site : le lien lu, sinon d'après le n° du produit."""
        if self.url:
            return self.url
        if self.id_product:
            return lien_produit(self.id_product)
        return ''

    def _libelle_du_nom(self) -> str:
        """Libellé tiré du nom du produit (« Nettoyant pour micro-ondes - 4812… »),
        quand la description n'a pas de titre : sans la réf. finale, coupé au type."""
        import re
        from ..utils.rapprochement_fiche.rapprochement import libelle_depuis_titre
        nom = re.sub(r'\s+[-–]\s+\S*\d\S*\s*$', '', (self.nom_produit or '').strip())
        return libelle_depuis_titre(nom) if nom else ''

    @property
    def id_product(self) -> Optional[int]:
        return getattr(self.rapprochement.identite, 'id_product', None)

    @property
    def sans_code_produit(self) -> bool:
        from ..utils.rapprochement_fiche.regles_import import SANS_CODE_PRODUIT
        return SANS_CODE_PRODUIT in self.plan.a_completer

    @property
    def reference_proposee(self) -> str:
        """Pièce proposée dans la fenêtre d'import : vide si elle est à saisir."""
        return '' if self.sans_code_produit else (self.plan.ref_piece or '')

    @property
    def nom_fichier(self) -> str:
        return f"fiche {self.id_product}" if self.id_product else "fiche du site"

    @property
    def libelle(self) -> str:
        """Libellé proposé : celui de l'outil, sinon le titre coupé (§ 10.11)."""
        i, p = self.rapprochement.identite, self.plan
        if p.libelle and p.remplacer_libelle:       # titre entier d'une reprise antérieure
            return p.libelle
        return i.libelle_outil or p.libelle or i.libelle or self._libelle_du_nom()

    # --- Relations de la fiche, pour la section « Succession » -------------------
    def remplace(self) -> List[str]:
        return list(dict.fromkeys(
            rp.ancienne for rp in self.rapprochement.remplacements
            if rp.sens == 'remplace' and rp.statut not in ('identique', 'cycle')))

    def remplacee_par(self) -> List[str]:
        return list(dict.fromkeys(
            rp.nouvelle for rp in self.rapprochement.remplacements
            if rp.sens == 'remplacee_par' and rp.statut not in ('identique', 'cycle')))[:1]

    def reference_associee(self) -> str:
        """2ᵉ référence du code produit (paire Whirlpool / Indesit / Beko, ligne 0)."""
        return next((e.reference for e in self.rapprochement.equivalences
                     if e.ligne == 0 and e.statut != 'ecartee'
                     and e.reference != self.plan.ref_piece), '')

    def equivalentes(self) -> List[str]:
        return list(dict.fromkeys(
            e.reference for e in self.rapprochement.equivalences
            if e.statut != 'ecartee' and e.reference != self.plan.ref_piece))

    def equivalentes_ecartees(self, remplace, remplacee_par, equivalentes,
                              ref: str = '') -> List[str]:
        """Équivalentes de la fiche supprimées des trois zones (ni gardées, ni
        déplacées vers « Remplace » / « Remplacée par ») : elles seront écartées."""
        gardees = {*remplace, *remplacee_par, *equivalentes, (ref or '').strip()}
        return [e for e in self.equivalentes() if e not in gardees]

    def apercu(self) -> Dict[str, object]:
        """Ce que la fenêtre d'import montre : comptes et premières lignes."""
        p, r = self.plan, self.rapprochement
        creations = {a.index for a in p.appareils_a_creer}
        retenues = set(p.a_refaire.indices) if p.a_refaire is not None else set()
        lies = {c for c, _ in p.liens if not isinstance(c, tuple)}
        lignes = []
        for i, a in enumerate(r.appareils):
            if i in creations:
                etat = "à créer"
            elif i in retenues:
                etat = "à refaire"
            elif a.appareil_id in lies or (a.appareil_id is None and a.proposition in lies):
                etat = "déjà lié" if a.lien == 'deja_lie' else "connu"
            elif a.lien == 'deja_couvert':
                etat = "couvert"
            else:
                etat = "non importé"
            lignes.append((etat, a.marque or a.marque_fiche or '?', a.ref_modele, a.nom, a.type))
        compte = {}
        for etat, *_ in lignes:
            compte[etat] = compte.get(etat, 0) + 1
        return {'titre': r.identite.libelle or self._libelle_du_nom(), 'id_product': self.id_product,
                'lignes': lignes, 'compte': compte, 'a_refaire': p.a_refaire,
                'non_importees': list(p.non_importees),
                'sans_code_produit': not p.ref_piece or p.a_completer}

    def resume_carte(self) -> str:
        """Une ligne pour la carte de la fiche (import d'un lot)."""
        a = self.apercu()
        compte = a['compte']
        morceaux = [f"{compte[e]} {libelle}" for e, libelle in (
            ("déjà lié", "déjà liés"), ("connu", "connus"), ("à créer", "à créer"),
            ("couvert", "couverts"), ("non importé", "non importés")) if compte.get(e)]
        return " · ".join(morceaux) or "aucun appareil (relations seules)"

    # --- Saisies de la fenêtre → plan ---------------------------------------------
    def appliquer_saisie(self, saisie) -> PlanEnregistrement:
        """`saisie` : la configuration rendue par la fenêtre d'import d'une fiche (réf.
        et libellé du fichier, Succession). Les relations y sont ensuite vidées : elles
        s'écrivent avec la fiche (origines, ordre), pas en double."""
        from ..utils.text_utils import decouper_refs
        chemin = self.nom_fichier
        plan = self.appliquer(saisie.individual_references.get(chemin),
                              saisie.individual_labels.get(chemin),
                              decouper_refs(saisie.succession_replaces),
                              decouper_refs(saisie.succession_replaced_by),
                              decouper_refs(saisie.equivalence_ref))
        saisie.succession_replaces = saisie.succession_replaced_by = None
        saisie.equivalence_ref = None
        return plan

    def appliquer(self, ref, libelle, remplace, remplacee_par, equivalentes) -> PlanEnregistrement:
        """Saisies de la fenêtre d'import (carte ou fiche seule) dans le plan. Les
        relations retirées ne sont pas écrites (une équivalente retirée est écartée et
        n'est plus proposée, sauf si elle a seulement changé de zone) ; celles
        ajoutées le sont."""
        from ..utils.rapprochement_fiche.decisions import forme_reference
        from ..utils.rapprochement_fiche.regles_import import SANS_CODE_PRODUIT
        p = self.plan
        # Sans code produit, la pièce est celle saisie : jamais la réf. interne par défaut
        ref = (ref or ('' if self.sans_code_produit else p.ref_piece) or '').strip()
        if ref and ref != p.ref_piece:
            ancienne = p.ref_piece
            p.ref_piece = ref
            if p.produit:
                p.produit['ref_piece'] = ref
            p.decisions_references = [(ref if d[0] == ancienne else d[0],) + tuple(d[1:])
                                      for d in p.decisions_references]
        if ref:
            p.a_completer = [m for m in p.a_completer if m != SANS_CODE_PRODUIT]
        libelle = (libelle or '').strip()
        outil = self.rapprochement.identite.libelle_outil or ''
        if not libelle or libelle == outil:
            p.libelle, p.remplacer_libelle = '', False          # libellé de l'outil gardé
        else:
            p.libelle, p.remplacer_libelle = libelle, bool(outil)

        remplace, remplacee_par, equivalentes = set(remplace), set(remplacee_par), set(equivalentes)
        de_la_fiche_r = set(self.remplace())
        de_la_fiche_rp = set(self.remplacee_par())
        p.remplacements = [(a, n) for a, n in p.remplacements
                           if (a in remplace) or (a == ref and n in remplacee_par)
                           or (a not in de_la_fiche_r and a != ref)]
        p.remplacements += [(a, ref) for a in sorted(remplace - de_la_fiche_r) if a != ref]
        p.remplacements += [(ref, n) for n in sorted(remplacee_par - de_la_fiche_rp) if n != ref]
        gardees = {a for a, _ in p.remplacements}
        p.rangs_remplace = [(a, k) for a, k in p.rangs_remplace if a in gardees]
        fiche_eq = set(self.equivalentes())
        retirees = fiche_eq - equivalentes
        # (« ⇄ » : la nouvelle référence de la pièce n'est pas son équivalente)
        p.equivalences = [e for e in p.equivalences if e not in retirees and e != ref]
        p.equivalences += [e for e in sorted(equivalentes - fiche_eq) if e != ref]
        p.origines = [o for o in p.origines if o[0] not in retirees and o[0] != ref]
        # Déplacée vers « Remplace » / « Remplacée par » (fiche mal structurée) :
        # n'est plus une équivalente, mais n'est pas écartée pour autant
        ecartees = self.equivalentes_ecartees(remplace, remplacee_par, equivalentes, ref)
        p.decisions_references += [(ref, e, 'ecartee', None, forme_reference(e))
                                   for e in sorted(ecartees)]
        return p
