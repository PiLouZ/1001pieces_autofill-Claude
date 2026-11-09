"""
Service Titre de fiche produit (v3.99.0)

Bouton « Titre » : génère le titre de la fiche produit de la référence
recherchée selon un profil de l'onglet « Titre » de la configuration des
exports, et le copie dans le presse-papiers.

Les données viennent de SEOService.preparer_donnees_fiche (mêmes règles que les
métas : référence la plus récente de la lignée, marques classées par nombre de
modèles, équivalentes en complément, libellé obligatoire). Seuls les types
diffèrent : tous ceux qui pèsent à peu près autant que le premier sont cités.
"""

from typing import Any, Dict, Optional, Tuple

from ..utils.qt_imports import QApplication

from src.core.logger import app_logger
from src.utils.titre_produit_generator import TitreProduitGenerator


class TitreProduitService:
    """Génération et copie du titre de fiche produit."""

    def __init__(self, main_window):
        self.main_window = main_window
        self.generateur = TitreProduitGenerator()

    def generer_titre(self, profile_name: Optional[str] = None) -> None:
        """Titre de la fiche recherchée selon le profil demandé (défaut : profil par défaut)."""
        try:
            self._generer_titre(profile_name)
        except Exception as e:
            app_logger.error(f"Titre: génération échouée : {e}", exc_info=True)
            self.main_window.statusbar.showMessage(f"Titre de fiche non généré : {e}", 8000)

    def calculer_titre(self, donnees: Dict[str, Any], profile_name: Optional[str]
                       ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """(résultat, profil) du titre des données préparées, selon le profil demandé.

        Partagé avec la fiche complète : même titre au caractère près.
        """
        config = getattr(self.main_window, 'export_config_service', None)
        if config is None:
            from src.services.export_config_service import DEFAULT_CONFIG
            profil = dict(DEFAULT_CONFIG['titre']['profiles'][0])
        else:
            profil = config.get_titre_profile(profile_name)

        types = self.generateur.types_proches(self.main_window.seo_service.poids_types_fiche(donnees),
                                              profil.get('max_types', 3))
        resultat = self.generateur.generer(profil, donnees['description'], types,
                                           donnees['fabricants'], donnees['reference'],
                                           appellations=self.main_window.seo_service.appellations())
        return resultat, profil

    # ─── Contexte / rendu / copie (bouton et aperçu d'export) ───────────────

    def contexte(self, interactif: bool = True, relancer=None) -> Optional[Dict[str, Any]]:
        """Données de la fiche recherchée, préparées une fois pour tous les gabarits.
        relancer : rappelé une fois la référence choisie (recherche multi-références)."""
        preparees = self.main_window.seo_service.preparer_donnees_fiche(
            "titre", "Référence pour le titre de fiche", interactif=interactif,
            relancer=relancer)
        if not preparees:
            return None
        donnees, ref_obsolete = preparees
        return {'donnees': donnees, 'ref_obsolete': ref_obsolete,
                'reference': donnees['reference']}

    def rendre(self, contexte: Dict[str, Any], profile_name: Optional[str]) -> Dict[str, Any]:
        """Titre selon le gabarit : {'html', 'resume', 'resultat', 'profil'}."""
        resultat, profil = self.calculer_titre(contexte['donnees'], profile_name)
        info = resultat['info']
        nb_marques = len(info['marques_retenues'])
        marques = f"{nb_marques} marque{'s' if nb_marques > 1 else ''}"
        if info['nb_marques_disponibles'] > nb_marques:
            marques += f" sur {info['nb_marques_disponibles']}"
        return {'html': resultat['titre'], 'resume': f"{resultat['longueur']} car., {marques}",
                'marques': marques, 'resultat': resultat, 'profil': profil}

    def copier(self, contexte: Dict[str, Any], profile_name: Optional[str]) -> None:
        """Copier le titre et le signaler (barre d'état + historique)."""
        rendu = self.rendre(contexte, profile_name)
        donnees, ref_obsolete = contexte['donnees'], contexte['ref_obsolete']
        resultat, profil, marques = rendu['resultat'], rendu['profil'], rendu['marques']
        titre = resultat['titre']
        info = resultat['info']
        QApplication.clipboard().setText(titre)

        status = f"Titre copié ({resultat['longueur']} car., {marques})"
        if ref_obsolete:
            status += f" [Supersédée → {donnees['reference']}]"

        detail = f"Titre: fiche '{donnees['reference']}'"
        if ref_obsolete:
            detail += f" (remplace {ref_obsolete})"
        detail += f" — profil « {profil.get('name', '')} »"
        detail += f"\n==> {titre}"
        detail += f"\n==> Longueur : {resultat['longueur']} car. ; {marques}"
        if not info['dans_la_limite']:
            detail += f" ; dépasse {profil.get('max_caracteres')} car. malgré le retrait des marques"

        self.main_window.user_interaction_service.add_to_history(detail)
        self.main_window.statusbar.showMessage(status, 4000)

    def _generer_titre(self, profile_name: Optional[str]) -> None:
        contexte = self.contexte(relancer=lambda: self.generer_titre(profile_name))
        if contexte:
            self.copier(contexte, profile_name)
