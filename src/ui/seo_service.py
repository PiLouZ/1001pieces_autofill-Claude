"""
Service SEO - Phase 2.15
Extrait de main_refactored.py pour centraliser la logique de génération SEO

Responsabilités:
- Génération de méta titles et descriptions optimisées SEO
- Récupération et analyse des données de recherche pour SEO
- Gestion des multi-références dans la génération SEO
- Interface avec le SEOGenerator pour optimisation du contenu
- Validation et formatage des données pour l'optimisation SEO
"""

from typing import Optional, Dict, Any, List, Tuple
from .qt_imports import QInputDialog, QApplication
from .qt_imports import QTimer, Qt

from src.core.config import Config
from src.core.logger import app_logger
from src.utils.seo_generator import SEOGenerator
from src.utils.error_handler import handle_seo_generation_errors, handle_seo_data_errors, handle_seo_dialog_errors

class SEOService:
    """
    Service spécialisé pour la génération et optimisation SEO
    
    Responsabilités:
    - Génération de méta titles et descriptions optimisées
    - Analyse des données de recherche pour contexte SEO
    - Gestion des multi-références et sélection utilisateur  
    - Interface utilisateur pour fonctionnalités SEO
    - Validation et optimisation du contenu généré
    """

    # Type d'appareil d'une fiche sans aucun appareil associé (cf. _type_majoritaire)
    TYPE_PAR_DEFAUT = "appareil électroménager"

    def __init__(self, main_window):
        self.main_window = main_window
        self.seo_generator = SEOGenerator()
        # Dernière formulation proposée par (genre, référence) : 0 = la méta fixe de
        # la référence, Maj+clic passe à la suivante.
        self._variantes: Dict[Tuple[str, str], int] = {}
    
    @handle_seo_generation_errors()
    def generate_meta_title(self) -> None:
        """Générer et copier un méta titre SEO optimisé (Maj+clic : autre formulation)"""
        autre_formulation = self._maj_enfoncee()
        preparees = self.preparer_donnees_fiche("title", "Référence pour Méta Title")
        if not preparees:
            return
        search_data, ref_obsolete = preparees

        result = self.seo_generator.generate_meta_title(
            reference=search_data['reference'],
            description=search_data['description'],
            type_appareil=search_data['type_appareil'],
            fabricants=search_data['fabricants'],
            variante=self._variante('title', search_data['reference'], autre_formulation),
        )
        # n_modeles non utilisé dans le title (pas assez de place) mais compté pour info

        QApplication.clipboard().setText(result['title'])

        length = result['length']
        nb_fabricants = result['info']['fabricants_count']
        fabricants_info = f"({nb_fabricants} fabricant{'s' if nb_fabricants > 1 else ''})" if nb_fabricants > 0 else ""
        largeur = f"{length} car., {result['info']['largeur_px']}/{SEOGenerator.TITLE_MAX_PX} px"
        status_msg = f"Méta titre copié ({largeur}) {fabricants_info}"
        if result['info']['truncated']:
            status_msg += " [Raccourci]"
        status_msg += self._libelle_variante(result['info'])
        if ref_obsolete:
            status_msg += f" [Supersédée → {search_data['reference']}]"

        detailed_message = f"SEO: Méta titre généré pour '{search_data['reference']}'"
        if ref_obsolete:
            detailed_message += f" (remplace {ref_obsolete})"
        detailed_message += f"\n==> Titre: {result['title']}"
        detailed_message += f"\n==> Longueur: {largeur}"
        if result['info']['fabricants_count'] > 0:
            detailed_message += f"\n==> Fabricants inclus: {result['info']['fabricants_count']}"
        if result['info']['truncated']:
            detailed_message += "\n==> Titre raccourci (mots entiers retirés pour tenir dans la largeur)"

        self.main_window.user_interaction_service.add_to_history(detailed_message)
        self.main_window.statusbar.showMessage(status_msg, 3000)
            
        
    
    @handle_seo_generation_errors()
    def generate_meta_description(self) -> None:
        """Générer et copier une méta description SEO (Maj+clic : autre formulation)"""
        autre_formulation = self._maj_enfoncee()
        preparees = self.preparer_donnees_fiche("description", "Référence pour Méta Description")
        if not preparees:
            return
        search_data, ref_obsolete = preparees

        # Compter les modèles compatibles (ref courante + prédécesseurs + groupe
        # d'équivalence : une équivalente équipe les mêmes besoins, décision client
        # 2026-10-08)
        db = self.main_window.db_manager
        all_refs_for_count = [search_data['reference']]
        try:
            preds = db.get_all_predecessors(search_data['reference'])
            all_refs_for_count.extend(preds)
        except Exception:
            preds = []
        try:
            groupe = db.get_equivalents(search_data['reference'])
            equivalentes = db.get_equivalents_hors_chaine(search_data['reference'])
        except Exception:
            groupe, equivalentes = [], []
        all_refs_for_count.extend(r for r in groupe if r not in all_refs_for_count)
        n_modeles = self._count_compatible_models(all_refs_for_count)
        anciennes_refs = self._anciennes_refs_principales(preds)
        equivalentes = self._refs_principales(equivalentes, SEOGenerator.MAX_EQUIVALENTES)

        result = self.seo_generator.generate_meta_description(
            reference=search_data['reference'],
            description=search_data['description'],
            type_appareil=search_data['type_appareil'],
            fabricants=search_data['fabricants'],
            n_modeles=n_modeles,
            anciennes_refs=anciennes_refs,  # toujours citées quand il y en a (décision client)
            equivalentes=equivalentes,      # idem ; 1 + 1 si la fiche a les deux
            variante=self._variante('description', search_data['reference'], autre_formulation),
        )

        QApplication.clipboard().setText(result['description'])

        length = result['length']
        largeur = f"{length} car., {result['info']['largeur_px']}/{SEOGenerator.DESCRIPTION_MAX_PX} px"
        status_msg = f"Méta description copiée ({largeur})"
        if result['info']['truncated']:
            status_msg += " [Raccourcie]"
        status_msg += self._libelle_variante(result['info'])
        if ref_obsolete:
            status_msg += f" [Supersédée → {search_data['reference']}]"

        detailed_message = f"SEO: Méta description générée pour '{search_data['reference']}'"
        if ref_obsolete:
            detailed_message += f" (remplace {ref_obsolete})"
        detailed_message += f"\n==> Description: {result['description']}"
        detailed_message += f"\n==> Longueur: {largeur}"
        if result['info']['truncated']:
            detailed_message += "\n==> Description raccourcie (mots entiers retirés pour tenir dans la largeur)"

        self.main_window.user_interaction_service.add_to_history(detailed_message)
        self.main_window.statusbar.showMessage(status_msg, 5000)
    
    def preparer_donnees_fiche(self, genre: str, titre_dialogue: str
                               ) -> Optional[Tuple[Dict[str, Any], Optional[str]]]:
        """
        Données d'une fiche pour une génération (méta title, méta description,
        titre de fiche) : (données, ancienne référence tapée ou None), ou None si
        la génération est refusée (refus déjà signalé).

        Recherche multi-références : choix de la référence. Puis référence
        courante de la chaîne de supersession, type et marques recalculés sur
        toute la lignée, libellé obligatoire, marques des équivalentes en
        complément.
        """
        multi_terms = self._get_multi_reference_terms()
        if multi_terms:
            selected_reference = self._show_reference_selection_dialog(
                titre_dialogue,
                f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                f"Choisissez la référence à utiliser pour la génération SEO :",
                multi_terms[0]
            )
            if not selected_reference:
                return None
            search_data = self._get_current_search_data_for_reference(selected_reference)
        else:
            search_data = self._get_current_search_data()

        if not search_data:
            self._signaler_absence_de_donnees(genre)
            return None

        required_keys = ['reference', 'description', 'type_appareil', 'fabricants']
        if not all(key in search_data for key in required_keys):
            self._signaler_refus(genre, self.main_window.search_input.text().strip(),
                                 f"Données incomplètes pour générer {self._QUOI[genre]}")
            return None

        # Résoudre la chaîne de supersession si nécessaire
        ref_obsolete = self._resolve_supersession(search_data)
        if ref_obsolete:
            search_data = self._enrich_with_supersession_data(search_data, ref_obsolete)
        if self._libelle_manquant(search_data, genre):
            return None
        self._completer_avec_equivalentes(search_data)
        return search_data, ref_obsolete

    def poids_types_fiche(self, search_data: Dict[str, Any]) -> Dict[str, int]:
        """
        Nombre de modèles par type d'appareil sur toute la famille de la fiche
        (lignée + références agrégées). Sans appareil associé ou si la base
        échoue : le seul type retenu pour la fiche (équivalentes ou défaut).
        """
        refs = list(search_data.get('refs_agregees') or [search_data['reference']])
        try:
            poids_types, _ = self._compter_appareils(refs)
        except Exception as e:
            app_logger.warning(f"Titre: types indisponibles pour {refs}: {e}")
            poids_types = {}
        return poids_types or {search_data['type_appareil']: 1}

    @staticmethod
    def _maj_enfoncee() -> bool:
        """Touche Maj enfoncée au moment du clic (lue avant tout dialogue modal)."""
        return bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)

    def _variante(self, genre: str, reference: str, autre_formulation: bool) -> int:
        """
        Clic simple : 0, la méta fixe de la référence. Maj+clic : la formulation
        suivante, à partir de la dernière proposée pour cette référence.
        """
        cle = (genre, reference)
        variante = self._variantes.get(cle, 0) + 1 if autre_formulation else 0
        self._variantes[cle] = variante
        return variante

    @staticmethod
    def _libelle_variante(info: Dict[str, Any]) -> str:
        """« [formulation 3/27] » hors formulation par défaut, sinon rien."""
        if not info.get('variante'):
            return ""
        return f" [formulation {info['variante'] + 1}/{info['nb_variantes']}]"

    def _anciennes_refs_principales(self, predecesseurs: List[str]) -> List[str]:
        """
        Les MAX_ANCIENNES_REFS anciennes références à citer : celles qui ont le plus
        de modèles compatibles (probablement les plus recherchées), à égalité par
        ordre alphabétique. Indépendant de la référence tapée : une fiche, une méta.
        """
        return self._refs_principales(predecesseurs, SEOGenerator.MAX_ANCIENNES_REFS)

    def _refs_principales(self, refs: List[str], maximum: int) -> List[str]:
        """
        Les `maximum` références de la liste qui ont le plus de modèles compatibles,
        à égalité par ordre alphabétique. Sert aux anciennes réfs et aux équivalentes.
        """
        predecesseurs = list(refs or [])
        if not predecesseurs:
            return []
        nb_modeles = {ref: 0 for ref in predecesseurs}
        try:
            placeholders = ','.join('?' * len(predecesseurs))
            query = f"""SELECT p.ref_piece, COUNT(DISTINCT pa.appareil_id)
                        FROM pieces p
                        JOIN piece_associations pa ON pa.piece_id = p.id
                        WHERE p.ref_piece IN ({placeholders})
                        GROUP BY p.ref_piece"""
            for ref, n in self.main_window.db_manager.execute_custom_query(query, predecesseurs):
                nb_modeles[ref] = n
        except Exception as e:
            app_logger.warning(f"SEO: impossible de classer les références {predecesseurs}: {e}")
        classees = sorted(nb_modeles, key=lambda r: (-nb_modeles[r], r))
        return classees[:maximum]

    def _count_compatible_models(self, refs: List[str]) -> int:
        """Compte le nombre de modèles d'appareils uniques compatibles avec les références données."""
        if not refs:
            return 0
        try:
            placeholders = ','.join('?' * len(refs))
            query = f"""SELECT COUNT(DISTINCT pa.appareil_id)
                        FROM piece_associations pa
                        JOIN pieces p ON pa.piece_id = p.id
                        WHERE p.ref_piece IN ({placeholders})"""
            result = self.main_window.db_manager.execute_custom_query(query, refs)
            return result[0][0] if result else 0
        except Exception as e:
            app_logger.warning(f"SEO: impossible de compter les modèles pour {refs}: {e}")
            return 0

    def _resolve_supersession(self, search_data: Dict[str, any]) -> Optional[str]:
        """
        Vérifie si la référence du search_data est obsolète.
        Si oui, résout la chaîne de supersession et met à jour search_data['reference']
        avec la référence courante finale.
        Retourne l'ancienne référence (ref_obsolete) si une résolution a eu lieu, None sinon.

        get_supersession_chain retourne une liste de strings [ref, ..., ref_courante].
        Si len == 1, la ref est déjà courante (pas obsolète).
        """
        ref = search_data['reference']
        try:
            chain = self.main_window.db_manager.get_supersession_chain(ref)
            # chain = ["ref", ..., "ref_courante"] — liste de strings
            if len(chain) > 1:
                ref_current = chain[-1]  # dernier élément = ref courante finale
                if ref_current and ref_current != ref:
                    search_data['reference'] = ref_current
                    return ref  # ref_obsolete = ref d'origine
        except Exception as e:
            app_logger.warning(f"SEO: impossible de résoudre la chaîne de supersession pour {ref}: {e}")
        return None

    def _enrich_with_supersession_data(self, search_data: Dict[str, any],
                                        ref_obsolete: str) -> Dict[str, any]:
        """
        Recalcule fabricants, type et libellé sur la famille de la référence courante :
        elle-même et tous ses prédécesseurs, plus les références déjà agrégées (recherche
        multi-références). Taper une ancienne référence donne ainsi la même méta que
        taper la référence courante : une fiche produit, une méta.
        """
        ref_current = search_data['reference']
        refs = self._avec_predecesseurs([ref_current])
        refs += [r for r in search_data.get('refs_agregees', []) if r not in refs]

        try:
            poids_types, poids_fabricants = self._compter_appareils(refs)

            if poids_types:
                search_data['type_appareil'] = self._type_majoritaire(poids_types)
            if poids_fabricants:
                search_data['fabricants'] = self._classer_fabricants(poids_fabricants)
            search_data['refs_agregees'] = refs

            # Le libellé est celui de la référence courante — même vide : la génération
            # est alors bloquée, comme si l'on avait tapé la référence courante.
            piece_courante = self._trouver_piece(ref_current)
            if piece_courante:
                search_data['description'] = piece_courante[1]

        except Exception as e:
            app_logger.warning(f"SEO: enrichissement supersession échoué pour {ref_current}: {e}")

        return search_data

    def _get_current_search_data(self) -> Optional[Dict[str, any]]:
        """Extraire les données de la recherche actuelle pour la génération SEO - Logique originale"""
        # Récupérer le terme de recherche actuel
        search_term = self.main_window.search_input.text().strip()
        if not search_term:
            return None

        # Pour les recherches multi-références, récupérer TOUTES les références
        search_terms = []
        if '||' in search_term:
            search_terms = [term.strip() for term in search_term.split('||') if term.strip()]
        else:
            search_terms = [search_term]

        # Utiliser la première référence pour la description et le titre
        piece = self._trouver_piece(search_terms[0])
        if not piece:
            return None  # Ne pas activer les boutons SEO si ce n'est pas une référence de pièce
        primary_reference, piece_description = piece
        search_terms = self._references_canoniques(search_terms)

        # Analyser les données du tableau pour extraire les informations des appareils
        if self.main_window.table.rowCount() == 0:
            return None

        # Extraire TOUS les fabricants et types depuis la base de données pour TOUTES les pièces,
        # prédécesseurs compris (ils héritent de leur couverture fabricants/types)
        all_refs = self._avec_predecesseurs(search_terms)
        poids_types, poids_fabricants = self._collecter_appareils(all_refs)

        return {
            'reference': primary_reference,
            'description': piece_description,
            'type_appareil': self._type_majoritaire(poids_types),
            'fabricants': self._classer_fabricants(poids_fabricants),
            'refs_agregees': all_refs,
        }
    
    def trouver_piece(self, reference: str) -> Optional[Tuple[str, str]]:
        """(référence telle qu'en base, libellé) — voir _trouver_piece. Public : sert
        aussi au raccourci ⌘⇧L (PieceManagementService.completer_libelle_recherche)."""
        return self._trouver_piece(reference)

    @handle_seo_data_errors()
    def _trouver_piece(self, reference: str) -> Optional[Tuple[str, str]]:
        """
        (référence telle qu'enregistrée, libellé — "" s'il est vide), ou None.
        Correspondance exacte, puis sans tenir compte de la casse (« as0015516 » →
        « AS0015516 ») : la méta porte toujours la référence écrite comme en base.
        Plus de recherche partielle (LIKE %réf%) : un fragment activait les boutons
        avec le libellé d'une autre pièce.
        """
        db = self.main_window.db_manager
        rows = db.execute_custom_query(
            "SELECT ref_piece, description FROM pieces WHERE ref_piece = ? LIMIT 1", [reference])
        if not rows:
            rows = db.execute_custom_query(
                "SELECT ref_piece, description FROM pieces WHERE ref_piece = ? COLLATE NOCASE LIMIT 2",
                [reference])
            if len(rows) != 1:  # absente, ou ambiguë (deux casses différentes en base)
                return None
        ref_piece, description = rows[0]
        return ref_piece, (description or "").strip()

    def _references_canoniques(self, references: List[str]) -> List[str]:
        """Références écrites comme en base quand elles y sont, telles quelles sinon."""
        canoniques = []
        for ref in references:
            piece = self._trouver_piece(ref)
            canoniques.append(piece[0] if piece else ref)
        return canoniques

    def _libelle_manquant(self, search_data: Dict[str, Any], genre: str) -> bool:
        """
        Bloque la génération si la pièce n'a pas de libellé (décision client) :
        l'ancien repli « pièce détachée » donnait « votre pièce détachée 00614351 ».
        """
        if search_data['description'].strip():
            return False
        from urllib.parse import quote
        from src.core.constants import UIConfig
        ref = search_data['reference']
        self._signaler_refus(
            genre, ref, f"Libellé manquant pour {ref} : complétez-le avant de générer "
                        f"{self._OBJET_LIBELLE.get(genre, 'la méta')}",
            lien=(UIConfig.LIEN_HISTORIQUE_LIBELLE + quote(ref, safe=""),
                  f"Compléter le libellé de {ref}  (⌘⇧L)"))
        return True

    def _signaler_absence_de_donnees(self, genre: str) -> None:
        terme = self.main_window.search_input.text().strip()
        if terme and '||' not in terme and '&&' not in terme and not self._trouver_piece(terme):
            message = f"Référence introuvable telle quelle : {terme}"
        else:
            message = f"Aucune recherche active pour générer {self._QUOI[genre]}"
        self._signaler_refus(genre, terme, message)

    _QUOI = {'title': "le méta titre", 'description': "la méta description",
             'titre': "le titre de fiche", 'fiche': "la fiche complète"}
    _NON_GENERE = {'title': "Méta titre non généré", 'description': "Méta description non générée",
                   'titre': "Titre de fiche non généré", 'fiche': "Fiche complète non générée"}
    # Préfixe de l'historique et objet du message « libellé manquant » ; SEO / la méta sinon
    _PREFIXE = {'titre': "Titre", 'fiche': "Fiche"}
    _OBJET_LIBELLE = {'titre': "le titre", 'fiche': "la fiche"}

    def _signaler_refus(self, genre: str, reference: str, raison: str,
                        lien: Optional[Tuple[str, str]] = None) -> None:
        """
        Explique pourquoi aucune méta n'a été générée, dans la barre d'état ET dans
        l'historique des opérations : c'est là, juste au-dessus des boutons, qu'arrive
        la méta quand elle réussit. Seul en bas à gauche de la fenêtre, loin des
        boutons, le message passait inaperçu (« les boutons ne font rien »).
        `lien` : action cliquable ajoutée sous l'entrée (ex. compléter le libellé).
        """
        self.main_window.statusbar.showMessage(raison, 8000)
        pour = f" pour '{reference}'" if reference else ""
        self.main_window.user_interaction_service.add_to_history(
            f"{self._PREFIXE.get(genre, 'SEO')}: {self._NON_GENERE[genre]}{pour}\n==> {raison}",
            lien=lien)

    @handle_seo_data_errors()
    def _get_multi_reference_terms(self) -> List[str]:
        """
        Détecter si la recherche contient plusieurs références séparées par des opérateurs
        """
        search_term = self.main_window.search_input.text().strip()
        if not search_term:
            return []

        # Détecter les opérateurs de recherche multiple
        if '||' in search_term:
            # Opérateur OR
            terms = [term.strip() for term in search_term.split('||') if term.strip()]
            # Filtrer pour ne garder que les références de pièce valides
            valid_terms = []
            for term in terms:
                piece = self._trouver_piece(term)
                if piece and piece[0] not in valid_terms:
                    valid_terms.append(piece[0])
            return valid_terms if len(valid_terms) > 1 else []

        elif '&&' in search_term:
            # Opérateur AND - plus complexe, pour l'instant on ne traite pas
            return []

        # Recherche simple
        return []
    
    @handle_seo_dialog_errors(return_value=None, title="Erreur dialogue sélection référence")
    def _show_reference_selection_dialog(self, title: str, message: str, default_reference: str) -> Optional[str]:
        """
        Afficher un dialogue de sélection de référence pour la génération SEO
        """
        # Récupérer toutes les références détectées
        multi_terms = self._get_multi_reference_terms()
        if not multi_terms:
            return default_reference

        # Utiliser QInputDialog avec une liste de choix
        reference, ok = QInputDialog.getItem(
            self.main_window,
            title,
            message,
            multi_terms,
            0,  # Index du choix par défaut
            False  # Non éditable
        )

        if ok and reference:
            return reference
        else:
            return None
    
    @handle_seo_generation_errors()
    def update_seo_buttons_state(self) -> None:
        """
        Mettre à jour l'état des boutons SEO selon la recherche actuelle
        """
        # Vérifier si la recherche actuelle est une référence de pièce
        search_term = self.main_window.search_input.text().strip()
        is_piece_search = False

        if search_term:
            # Vérifier si c'est une référence de pièce ou contient des références
            if self._trouver_piece(search_term):
                is_piece_search = True
            elif self._get_multi_reference_terms():
                is_piece_search = True

        # Mettre à jour l'état des boutons SEO
        if hasattr(self.main_window, 'meta_title_btn'):
            self.main_window.meta_title_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'meta_desc_btn'):
            self.main_window.meta_desc_btn.setEnabled(is_piece_search)
        # Le titre de fiche repose sur les mêmes données que les métas
        if hasattr(self.main_window, 'titre_btn'):
            self.main_window.titre_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'fiche_btn'):
            self.main_window.fiche_btn.setEnabled(is_piece_search)
    
    @handle_seo_generation_errors()
    def cleanup(self) -> None:
        """
        Nettoyer les ressources du service SEO
        """
        # Nettoyer le générateur SEO si nécessaire
        if hasattr(self.seo_generator, 'cleanup'):
            self.seo_generator.cleanup()
    
    @handle_seo_data_errors()
    def _get_current_search_data_for_reference(self, specific_reference: str) -> Optional[Dict[str, any]]:
        """Extraire les données pour une référence spécifique (utilisé pour les multi-références) - Logique originale"""
        # Récupérer le terme de recherche original
        original_search_term = self.main_window.search_input.text().strip()

        # Si c'est une recherche multi-références, utiliser les données d'une référence existante
        if '||' in original_search_term or '&&' in original_search_term:
            # Diviser selon l'opérateur utilisé
            if '||' in original_search_term:
                references = [ref.strip() for ref in original_search_term.split('||') if ref.strip()]
            else:  # && présent
                references = [ref.strip() for ref in original_search_term.split('&&') if ref.strip()]

            app_logger.info(f"Génération méta pour multi-références: {references}")

            # Étendre avec les prédécesseurs pour hériter leur couverture fabricants/types
            all_refs_multi = self._avec_predecesseurs(self._references_canoniques(references))

            # Les références d'une recherche « A || B » désignent une même pièce : leurs
            # appareils sont agrégés (directes + prédécesseurs). Le libellé, lui, est celui
            # de la référence choisie ; à défaut (vide), le premier renseigné.
            piece_description = ""
            for ref in [specific_reference] + all_refs_multi:
                piece = self._trouver_piece(ref)
                if piece and piece[1]:
                    piece_description = piece[1]
                    break

            poids_types, poids_fabricants = self._collecter_appareils(all_refs_multi)

            if piece_description and (poids_types or poids_fabricants):
                type_appareil = self._type_majoritaire(poids_types)
                fabricants_list = self._classer_fabricants(poids_fabricants)

                app_logger.info(f"Multi-ref agrégé: type={type_appareil}, fabricants={len(fabricants_list)}")

                return {
                    'reference': specific_reference,
                    'description': piece_description,
                    'type_appareil': type_appareil,
                    'fabricants': fabricants_list,
                    'refs_agregees': all_refs_multi,
                }
            else:
                app_logger.warning("Aucune donnée valide trouvée dans la recherche multi-références")

        # Vérifier si c'est une référence de pièce valide (cas normal). Une référence
        # absente de la base ne produit plus de méta de secours (« Pièce détachée X »).
        piece = self._trouver_piece(specific_reference)
        if not piece:
            return None
        specific_reference, piece_description = piece

        # Analyser les données du tableau pour extraire les informations des appareils
        if self.main_window.table.rowCount() == 0:
            return None

        # Extraire TOUS les fabricants et types depuis la base de données pour cette pièce,
        # prédécesseurs compris (ils héritent de leur couverture fabricants/types)
        all_refs_single = self._avec_predecesseurs([specific_reference])
        poids_types, poids_fabricants = self._collecter_appareils(all_refs_single)

        return {
            'reference': specific_reference,
            'description': piece_description,
            'type_appareil': self._type_majoritaire(poids_types),
            'fabricants': self._classer_fabricants(poids_fabricants),
            'refs_agregees': all_refs_single,
        }

    # ── Agrégation des appareils compatibles (socle commun des 4 chemins) ──

    def _avec_predecesseurs(self, refs: List[str]) -> List[str]:
        """Références données suivies de tous leurs prédécesseurs (sans doublon ajouté)."""
        all_refs = list(refs)
        for ref in refs:
            try:
                for pred in self.main_window.db_manager.get_all_predecessors(ref):
                    if pred not in all_refs:
                        all_refs.append(pred)
            except Exception:
                pass
        return all_refs

    def _completer_avec_equivalentes(self, search_data: Dict[str, Any]) -> None:
        """
        Compléter (en place) les marques et le type de la fiche avec ceux de ses réfs
        équivalentes (décision client 2026-10-08).

        EN COMPLÉMENT seulement :
        - marques : celles de la fiche restent en tête, dans leur ordre ; celles des
          équivalentes suivent. Le générateur garde les MAX_MARQUES premières, donc
          une fiche qui a déjà 3 marques propres ne change pas ;
        - type : repris des équivalentes uniquement si la fiche n'en a pas (défaut
          « appareil électroménager », faute d'appareil associé en propre).
        Fusionner les modèles évinçait les marques de la fiche (00154686, réf. Bosch,
        ne citait plus que De Dietrich) et changeait le type (« four » → « four
        vapeur ») : essai écarté.
        """
        fabricants = list(search_data.get('fabricants') or [])
        famille = list(search_data.get('refs_agregees') or [search_data['reference']])
        db = self.main_window.db_manager
        equivalentes = []
        for ref in famille:
            try:
                for autre in db.get_equivalents(ref):
                    if autre not in famille and autre not in equivalentes:
                        equivalentes.append(autre)
            except Exception:
                pass
        if not equivalentes:
            return
        try:
            poids_types, poids = self._compter_appareils(equivalentes)
        except Exception as e:
            app_logger.warning(f"SEO: marques des équivalentes indisponibles pour {equivalentes}: {e}")
            return
        propres = [] if fabricants == ["multi-marques"] else fabricants
        ajout = [m for m in self._par_poids(poids) if m not in propres]
        search_data['fabricants'] = (propres + ajout) or fabricants
        if search_data.get('type_appareil') == self.TYPE_PAR_DEFAUT and poids_types:
            search_data['type_appareil'] = self._type_majoritaire(poids_types)

    def _compter_appareils(self, refs: List[str]) -> Tuple[Dict[str, int], Dict[str, int]]:
        """
        Nombre de modèles compatibles par type d'appareil et par fabricant, toutes
        références confondues (un modèle associé à deux d'entre elles compte une fois).
        Les erreurs SQL remontent à l'appelant.
        """
        poids_types: Dict[str, int] = {}
        poids_fabricants: Dict[str, int] = {}
        if not refs:
            return poids_types, poids_fabricants
        query = Config.get_query('device_counts_for_pieces',
                                 placeholders=','.join('?' * len(refs)))
        for type_val, manufacturer, nb_modeles in self.main_window.db_manager.execute_custom_query(query, refs):
            if type_val:
                poids_types[type_val] = poids_types.get(type_val, 0) + nb_modeles
            if manufacturer:
                poids_fabricants[manufacturer] = poids_fabricants.get(manufacturer, 0) + nb_modeles
        return poids_types, poids_fabricants

    def _collecter_appareils(self, refs: List[str]) -> Tuple[Dict[str, int], Dict[str, int]]:
        """
        Comme _compter_appareils, mais si la base échoue, se rabat sur les lignes visibles
        du tableau (20 au plus) : chaque ligne est un modèle et pèse 1.
        """
        try:
            return self._compter_appareils(refs)
        except Exception as e:
            app_logger.error(f"Erreur récupération fabricants pour {refs}: {e}")

        poids_types: Dict[str, int] = {}
        poids_fabricants: Dict[str, int] = {}
        for row in range(min(self.main_window.table.rowCount(), 20)):
            if not self.main_window.table.isRowHidden(row):
                type_item = self.main_window.table.item(row, 0)
                if type_item and type_item.text().strip():
                    t = type_item.text().strip()
                    poids_types[t] = poids_types.get(t, 0) + 1
                fabricant_item = self.main_window.table.item(row, 1)
                if fabricant_item and fabricant_item.text().strip():
                    m = fabricant_item.text().strip()
                    poids_fabricants[m] = poids_fabricants.get(m, 0) + 1
        return poids_types, poids_fabricants

    @staticmethod
    def _par_poids(poids: Dict[str, int]) -> List[str]:
        """Clés par poids décroissant ; à égalité, ordre alphabétique (résultat stable)."""
        return [k for k, _ in sorted(poids.items(), key=lambda x: (-x[1], x[0].casefold(), x[0]))]

    @classmethod
    def _type_majoritaire(cls, poids_types: Dict[str, int],
                          defaut: str = None) -> str:
        """Type d'appareil qui couvre le plus de modèles, ou `defaut` si aucun."""
        return cls._par_poids(poids_types)[0] if poids_types else (defaut or cls.TYPE_PAR_DEFAUT)

    @classmethod
    def _classer_fabricants(cls, poids_fabricants: Dict[str, int]) -> List[str]:
        """Fabricants du plus grand au plus petit nombre de modèles compatibles."""
        return cls._par_poids(poids_fabricants) if poids_fabricants else ["multi-marques"]