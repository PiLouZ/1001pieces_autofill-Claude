"""
Enregistrement d'une fiche du site après validation de l'aperçu
(CDC docs/cdc_import_fiches_site.md, § 7.5, étape 3)

Le service écrit un `PlanEnregistrement` (src/utils/rapprochement_fiche/decisions.py)
par les briques du tronc commun d'import, jamais par un chemin parallèle :
- appareils créés par `ImportManager._batch_insert_devices` (même requête,
  même verrou, même invalidation du cache de comptage que l'import PDF/CSV) ;
- remplacements et équivalences par `import_relations.apply_relations`
  (fantômes, obsolescence des anciennes, propagation du libellé) ;
- caches invalidés comme après un import, puis `EventDrivenSaveService`.

Ce qui est propre à la reprise (pièce fantôme → réelle, liens avec provenance,
étiquettes d'origine, produit du site, décisions consignées) passe par les
primitives de `DatabaseFichesSiteMixin`, sous le verrou de la base.

Ajout seul (§ 6.2) : rien n'est supprimé. Relire une fiche ne crée aucun
doublon : un appareil créé ressort « exact » à la relecture, un lien présent ne
fait que compléter sa provenance, une équivalence présente est ignorée.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

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

    def enregistrer(self, plan: PlanEnregistrement) -> ResultatEnregistrement:
        res = ResultatEnregistrement()
        if not plan.pret:
            res.ok = False
            res.erreur = "aperçu non validé : " + "; ".join(plan.en_attente + plan.a_completer)
            return res
        try:
            self._ecrire(plan, res)
        except Exception as e:      # le plan reste rejouable : tout y est idempotent
            app_logger.error(f"[Fiche site] Enregistrement de {plan.ref_piece} interrompu : {e}")
            res.ok, res.erreur = False, str(e)
        self._apres_ecriture(res)
        app_logger.info(f"[Fiche site] {plan.ref_piece} : {res.resume()}")
        return res

    # -------------------------------------------------------------------------
    def _ecrire(self, plan: PlanEnregistrement, res: ResultatEnregistrement,
                nouveaux: Optional[Dict[int, int]] = None):
        """Écrit le plan d'une fiche. `nouveaux` (import en masse) : appareils du plan
        déjà créés pour tout le lot (index de la ligne → id) ; sinon ils sont créés ici."""
        db = self.db
        # 1. La pièce : créée réelle, ou fantôme → réelle (liens hérités inchangés)
        with db._query_lock:
            piece_id, res.piece = db._creer_ou_promouvoir_piece(
                plan.ref_piece, plan.libelle, plan.remplacer_libelle)
            db.conn.commit()

        # 2. Appareils à créer : brique d'insertion du tronc d'import
        if nouveaux is None:
            nouveaux = self.creer_appareils(plan.appareils_a_creer, res)
        # 3 à 5. Liens, relations, origines, produit, décisions
        self._ecrire_suite(plan, res, piece_id, nouveaux)

    def creer_appareils(self, appareils, res: Optional[ResultatEnregistrement] = None
                        ) -> Dict[int, int]:
        """Crée les appareils (AppareilACreer) par la brique d'insertion du tronc
        d'import ; retourne index de la ligne → id."""
        nouveaux: Dict[int, int] = {}
        if appareils:
            from ..core.import_manager import ImportManager
            lot = [{'type': a.type, 'manufacturer': a.marque, 'ref_modele': a.ref_modele,
                    'commercial_ref': a.nom, 'other_ref': '', 'notes': '', 'category': ''}
                   for a in appareils]
            ids = ImportManager(self.db)._batch_insert_devices(lot)
            if len(ids) != len(lot):
                raise RuntimeError(f"{len(lot)} appareils à créer, {len(ids)} créés")
            nouveaux = {a.index: i for a, i in zip(appareils, ids)}
            if res is not None:
                res.appareils_crees = len(ids)
        return nouveaux

    def _ecrire_suite(self, plan: PlanEnregistrement, res: ResultatEnregistrement,
                      piece_id: int, nouveaux: Dict[int, int]):
        db = self.db
        # 3. Liens avec provenance (§ 5.7)
        liens = []
        for cible, provenance in plan.liens:
            ident = nouveaux.get(cible[1]) if isinstance(cible, tuple) else cible
            if ident is not None:
                liens.append((ident, provenance))
        with db._query_lock:
            compte = db._ajouter_liens_provenance(piece_id, liens)
            db.conn.commit()
        res.liens_crees, res.liens_completes, res.liens_inchanges = (
            compte['crees'], compte['completes'], compte['inchanges'])

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

    def _apres_ecriture(self, res: ResultatEnregistrement, source: str = "fiche_site"):
        """Caches invalidés comme après un import, puis sauvegarde événementielle
        (thread principal : la sauvegarde passe par des minuteries Qt)."""
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
