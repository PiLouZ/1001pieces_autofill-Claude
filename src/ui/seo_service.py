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
from .qt_imports import QTimer

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
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.seo_generator = SEOGenerator()
    
    @handle_seo_generation_errors()
    def generate_meta_title(self) -> None:
        """Générer et copier un méta titre SEO optimisé"""
        multi_terms = self._get_multi_reference_terms()
        if multi_terms:
            selected_reference = self._show_reference_selection_dialog(
                "Référence pour Méta Title",
                f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                f"Choisissez la référence à utiliser pour la génération SEO :",
                multi_terms[0]
            )
            if not selected_reference:
                return
            search_data = self._get_current_search_data_for_reference(selected_reference)
        else:
            search_data = self._get_current_search_data()

        if not search_data:
            self.main_window.statusbar.showMessage("Aucune recherche active pour générer le méta titre", 3000)
            return

        required_keys = ['reference', 'description', 'type_appareil', 'fabricants']
        if not all(key in search_data for key in required_keys):
            self.main_window.statusbar.showMessage("Données incomplètes pour générer le méta titre", 3000)
            return

        # Résoudre la chaîne de supersession si nécessaire
        ref_obsolete = self._resolve_supersession(search_data)
        if ref_obsolete:
            search_data = self._enrich_with_supersession_data(search_data, ref_obsolete)

        result = self.seo_generator.generate_meta_title(
            reference=search_data['reference'],
            description=search_data['description'],
            type_appareil=search_data['type_appareil'],
            fabricants=search_data['fabricants'],
        )
        # n_modeles non utilisé dans le title (pas assez de place) mais compté pour info

        QApplication.clipboard().setText(result['title'])

        length = result['length']
        fabricants_info = f"({result['info']['fabricants_count']} fabricants)" if result['info']['fabricants_count'] > 0 else ""
        status_msg = f"Méta titre copié ({length}/60 caractères) {fabricants_info}"
        if result['info']['truncated']:
            status_msg += " [Tronqué]"
        if ref_obsolete:
            status_msg += f" [Supersédée → {search_data['reference']}]"

        detailed_message = f"SEO: Méta titre généré pour '{search_data['reference']}'"
        if ref_obsolete:
            detailed_message += f" (remplace {ref_obsolete})"
        detailed_message += f"\n==> Titre: {result['title']}"
        detailed_message += f"\n==> Longueur: {length}/60 caractères"
        if result['info']['fabricants_count'] > 0:
            detailed_message += f"\n==> Fabricants inclus: {result['info']['fabricants_count']}"
        if result['info']['truncated']:
            detailed_message += "\n==> Titre tronqué"

        self.main_window.user_interaction_service.add_to_history(detailed_message)
        self.main_window.statusbar.showMessage(status_msg, 3000)
            
        
    
    @handle_seo_generation_errors()
    def generate_meta_description(self) -> None:
        """Générer et copier une méta description SEO aléatoire"""
        multi_terms = self._get_multi_reference_terms()
        if multi_terms:
            selected_reference = self._show_reference_selection_dialog(
                "Référence pour Méta Description",
                f"Plusieurs références détectées ({', '.join(multi_terms)}).\n"
                f"Choisissez la référence à utiliser pour la génération SEO :",
                multi_terms[0]
            )
            if not selected_reference:
                return
            search_data = self._get_current_search_data_for_reference(selected_reference)
        else:
            search_data = self._get_current_search_data()

        if not search_data:
            self.main_window.statusbar.showMessage("Aucune recherche active pour générer la méta description", 3000)
            return

        required_keys = ['reference', 'description', 'type_appareil', 'fabricants']
        if not all(key in search_data for key in required_keys):
            self.main_window.statusbar.showMessage("Données incomplètes pour générer la méta description", 3000)
            return

        # Résoudre la chaîne de supersession si nécessaire
        ref_obsolete = self._resolve_supersession(search_data)
        if ref_obsolete:
            search_data = self._enrich_with_supersession_data(search_data, ref_obsolete)

        # Compter les modèles compatibles (ref courante + prédécesseurs)
        all_refs_for_count = [search_data['reference']]
        try:
            preds = self.main_window.db_manager.get_all_predecessors(search_data['reference'])
            all_refs_for_count.extend(preds)
        except Exception:
            pass
        n_modeles = self._count_compatible_models(all_refs_for_count)

        result = self.seo_generator.generate_meta_description(
            reference=search_data['reference'],
            description=search_data['description'],
            type_appareil=search_data['type_appareil'],
            fabricants=search_data['fabricants'],
            n_modeles=n_modeles,
            ref_old=ref_obsolete,  # None si la réf n'est pas supersédée
        )

        QApplication.clipboard().setText(result['description'])

        length = result['length']
        status_msg = f"Méta description copiée ({length}/150 caractères)"
        if result['info']['truncated']:
            status_msg += " [Tronquée]"
        if ref_obsolete:
            status_msg += f" [Supersédée → {search_data['reference']}]"

        detailed_message = f"SEO: Méta description générée pour '{search_data['reference']}'"
        if ref_obsolete:
            detailed_message += f" (remplace {ref_obsolete})"
        detailed_message += f"\n==> Description: {result['description']}"
        detailed_message += f"\n==> Longueur: {length}/150 caractères"
        if result['info']['truncated']:
            detailed_message += "\n==> Description tronquée"

        self.main_window.user_interaction_service.add_to_history(detailed_message)
        self.main_window.statusbar.showMessage(status_msg, 5000)
    
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
        Enrichit les fabricants et le type avec les données de la référence courante.
        La description reste celle de la référence originale recherchée.
        """
        ref_current = search_data['reference']
        fabricants_query = Config.get_query('devices_for_piece')
        from collections import Counter
        types_list = list()
        # Initialiser avec count=1 pour les fabricants déjà présents
        fabricants_count = {f: 1 for f in search_data.get('fabricants', [])}

        try:
            rows = self.main_window.db_manager.execute_custom_query(fabricants_query, [ref_current])
            for type_val, manufacturer in rows:
                if type_val and type_val.strip():
                    types_list.append(type_val.strip())
                if manufacturer and manufacturer.strip():
                    m = manufacturer.strip()
                    fabricants_count[m] = fabricants_count.get(m, 0) + 1

            if types_list:
                type_counter = Counter(types_list)
                search_data['type_appareil'] = type_counter.most_common(1)[0][0]

            search_data['fabricants'] = [f for f, _ in sorted(fabricants_count.items(), key=lambda x: -x[1])] \
                if fabricants_count else ["multi-marques"]

            # Mettre à jour la description avec celle de la référence courante si disponible
            desc_current = self._get_piece_description_from_reference(ref_current)
            if desc_current:
                search_data['description'] = desc_current

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
        primary_reference = search_terms[0]

        # Vérifier si c'est une référence de pièce (recherche dans la table pieces)
        piece_description = self._get_piece_description_from_reference(primary_reference)
        if not piece_description:
            return None  # Ne pas activer les boutons SEO si ce n'est pas une référence de pièce

        # Analyser les données du tableau pour extraire les informations des appareils
        if self.main_window.table.rowCount() == 0:
            return None

        # Extraire TOUS les fabricants et types depuis la base de données pour TOUTES les pièces
        from collections import Counter
        types_appareil_list = []
        fabricants_count: Dict[str, int] = {}  # fabricant → nb d'occurrences (pour tri par pertinence)

        fabricants_query = Config.get_query('devices_for_piece')

        # Étendre avec les prédécesseurs pour hériter leur couverture fabricants/types
        all_refs = list(search_terms)
        for ref in search_terms:
            try:
                predecessors = self.main_window.db_manager.get_all_predecessors(ref)
                for pred in predecessors:
                    if pred not in all_refs:
                        all_refs.append(pred)
            except Exception:
                pass

        try:
            for ref in all_refs:
                all_data = self.main_window.db_manager.execute_custom_query(fabricants_query, [ref])
                for type_val, manufacturer in all_data:
                    if type_val and type_val.strip():
                        types_appareil_list.append(type_val.strip())
                    if manufacturer and manufacturer.strip():
                        m = manufacturer.strip()
                        fabricants_count[m] = fabricants_count.get(m, 0) + 1

        except Exception as e:
            app_logger.error(f"Erreur récupération fabricants pour {all_refs}: {e}")

            # Fallback: utiliser les données visibles du tableau si la requête échoue
            for row in range(min(self.main_window.table.rowCount(), 20)):
                if not self.main_window.table.isRowHidden(row):
                    type_item = self.main_window.table.item(row, 0)
                    if type_item and type_item.text().strip():
                        types_appareil_list.append(type_item.text().strip())
                    fabricant_item = self.main_window.table.item(row, 1)
                    if fabricant_item and fabricant_item.text().strip():
                        m = fabricant_item.text().strip()
                        fabricants_count[m] = fabricants_count.get(m, 0) + 1

        reference = primary_reference
        description = piece_description

        if types_appareil_list:
            type_counter = Counter(types_appareil_list)
            type_appareil = type_counter.most_common(1)[0][0]
        else:
            type_appareil = "appareil électroménager"

        # Tri par fréquence décroissante (les marques les plus compatibles en premier)
        fabricants_list = [f for f, _ in sorted(fabricants_count.items(), key=lambda x: -x[1])] \
            if fabricants_count else ["multi-marques"]

        return {
            'reference': reference,
            'description': description,
            'type_appareil': type_appareil,
            'fabricants': fabricants_list
        }
    
    @handle_seo_data_errors()
    def _get_piece_description_from_reference(self, reference: str) -> Optional[str]:
        """
        Récupérer la description d'une pièce à partir de sa référence
        Utilise la même logique que _is_piece_reference_search()
        """
        # D'abord essayer de récupérer le libellé directement depuis la table pieces
        query = "SELECT description FROM pieces WHERE ref_piece = ? LIMIT 1"
        result = self.main_window.db_manager.execute_custom_query(query, [reference])

        if result:
            description = result[0][0]
            # Vérifier que la description n'est pas None ou vide
            if description and description.strip():
                return description.strip()
            else:
                # Si la description est vide, utiliser une description générique
                return "pièce détachée"

        # Essayer une recherche partielle si la recherche exacte échoue
        query_partial = "SELECT description FROM pieces WHERE ref_piece LIKE ? LIMIT 1"
        result_partial = self.main_window.db_manager.execute_custom_query(query_partial, [f"%{reference}%"])

        if result_partial:
            description = result_partial[0][0]
            if description and description.strip():
                return description.strip()
            else:
                return "pièce détachée"

        return None  # Aucune pièce trouvée
    
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
                if self._get_piece_description_from_reference(term):
                    valid_terms.append(term)
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
            if self._get_piece_description_from_reference(search_term):
                is_piece_search = True
            elif self._get_multi_reference_terms():
                is_piece_search = True

        # Mettre à jour l'état des boutons SEO
        if hasattr(self.main_window, 'meta_title_btn'):
            self.main_window.meta_title_btn.setEnabled(is_piece_search)
        if hasattr(self.main_window, 'meta_desc_btn'):
            self.main_window.meta_desc_btn.setEnabled(is_piece_search)
    
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
            all_refs_multi = list(references)
            for ref in references:
                try:
                    predecessors = self.main_window.db_manager.get_all_predecessors(ref)
                    for pred in predecessors:
                        if pred not in all_refs_multi:
                            all_refs_multi.append(pred)
                except Exception:
                    pass

            # Récupérer les données agrégées de TOUTES les références (directes + prédécesseurs)
            from collections import Counter
            all_types = []
            all_manufacturers_count: Dict[str, int] = {}
            piece_description = None

            for ref in all_refs_multi:
                desc = self._get_piece_description_from_reference(ref)
                if desc and not piece_description:
                    piece_description = desc

                fabricants_query = Config.get_query('devices_for_piece')
                try:
                    ref_data = self.main_window.db_manager.execute_custom_query(fabricants_query, [ref])
                    for type_val, manufacturer in ref_data:
                        if type_val and type_val.strip():
                            all_types.append(type_val.strip())
                        if manufacturer and manufacturer.strip():
                            m = manufacturer.strip()
                            all_manufacturers_count[m] = all_manufacturers_count.get(m, 0) + 1
                    app_logger.info(f"Référence {ref}: {len(ref_data)} appareils trouvés")
                except Exception as e:
                    app_logger.error(f"Erreur récupération données pour {ref}: {e}")

            if piece_description and (all_types or all_manufacturers_count):
                if all_types:
                    type_counter = Counter(all_types)
                    type_appareil = type_counter.most_common(1)[0][0]
                else:
                    type_appareil = "appareil électroménager"

                fabricants_list = [f for f, _ in sorted(all_manufacturers_count.items(), key=lambda x: -x[1])] \
                    if all_manufacturers_count else ["multi-marques"]

                app_logger.info(f"Multi-ref agrégé: type={type_appareil}, fabricants={len(fabricants_list)}")

                return {
                    'reference': specific_reference,
                    'description': piece_description,
                    'type_appareil': type_appareil,
                    'fabricants': fabricants_list
                }
            else:
                app_logger.warning("Aucune donnée valide trouvée dans la recherche multi-références")

        # Vérifier si c'est une référence de pièce valide (cas normal)
        piece_description = self._get_piece_description_from_reference(specific_reference)

        # Si la référence n'existe pas en BDD, créer des données par défaut
        if not piece_description:
            return {
                'reference': specific_reference,
                'description': f"Pièce détachée {specific_reference}",
                'type_appareil': "appareil électroménager",
                'fabricants': ["multi-marques"]
            }

        # Analyser les données du tableau pour extraire les informations des appareils
        if self.main_window.table.rowCount() == 0:
            return None

        # Extraire TOUS les fabricants et types depuis la base de données pour cette pièce
        from collections import Counter
        types_appareil_list2 = []
        fabricants_count2: Dict[str, int] = {}

        fabricants_query = Config.get_query('devices_for_piece')

        # Étendre avec les prédécesseurs pour hériter leur couverture fabricants/types
        all_refs_single = [specific_reference]
        try:
            predecessors = self.main_window.db_manager.get_all_predecessors(specific_reference)
            for pred in predecessors:
                if pred not in all_refs_single:
                    all_refs_single.append(pred)
        except Exception:
            pass

        try:
            for ref in all_refs_single:
                all_data = self.main_window.db_manager.execute_custom_query(fabricants_query, [ref])
                for type_val, manufacturer in all_data:
                    if type_val and type_val.strip():
                        types_appareil_list2.append(type_val.strip())
                    if manufacturer and manufacturer.strip():
                        m = manufacturer.strip()
                        fabricants_count2[m] = fabricants_count2.get(m, 0) + 1

        except Exception as e:
            app_logger.error(f"Erreur récupération fabricants pour {all_refs_single}: {e}")

            for row in range(min(self.main_window.table.rowCount(), 20)):
                if not self.main_window.table.isRowHidden(row):
                    type_item = self.main_window.table.item(row, 0)
                    if type_item and type_item.text().strip():
                        types_appareil_list2.append(type_item.text().strip())
                    fabricant_item = self.main_window.table.item(row, 1)
                    if fabricant_item and fabricant_item.text().strip():
                        m = fabricant_item.text().strip()
                        fabricants_count2[m] = fabricants_count2.get(m, 0) + 1

        if types_appareil_list2:
            type_counter2 = Counter(types_appareil_list2)
            type_appareil = type_counter2.most_common(1)[0][0]
        else:
            type_appareil = "appareil électroménager"

        fabricants_list = [f for f, _ in sorted(fabricants_count2.items(), key=lambda x: -x[1])] \
            if fabricants_count2 else ["multi-marques"]

        return {
            'reference': specific_reference,
            'description': piece_description,
            'type_appareil': type_appareil,
            'fabricants': fabricants_list
        }