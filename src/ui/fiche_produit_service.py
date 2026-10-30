"""
Service Fiche produit complète

Bouton « Fiche complète » : assemble tout le code HTML de la fiche de la
référence recherchée selon un profil de l'onglet « Fiche » de la configuration
des exports, et le copie dans le presse-papiers.

- Titre : celui du bouton Titre (TitreProduitService.calculer_titre), avec le
  gabarit choisi dans le profil.
- Code produit : la référence tapée ; si elle est remplacée, la plus récente
  de sa lignée (comme le Titre).
- « Remplace les références » : toutes ses anciennes références.
- « Références équivalentes » : une ligne par équivalente hors lignée, suivie
  de ses propres anciennes références, de la plus fournie en appareils à la
  moins fournie.
- Marques et appareils : ce qu'affiche le tableau (bandeaux et filtres de
  colonnes), comme les boutons HTML Marques / Détails.
"""

from typing import List, Optional, Tuple

from .qt_imports import QApplication

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
        seo = self.main_window.seo_service
        preparees = seo.preparer_donnees_fiche("fiche", "Référence pour la fiche complète")
        if not preparees:
            return
        donnees, ref_obsolete = preparees
        reference = donnees['reference']

        appareils = self.main_window.export_manager.donnees_tableau()
        if not appareils:
            seo._signaler_refus("fiche", reference, "Aucun appareil affiché dans le tableau")
            return

        profil = self.main_window.export_config_service.get_fiche_profile(profile_name)
        resultat_titre, _ = self.main_window.titre_produit_service.calculer_titre(
            donnees, profil.get('titre_profile') or None)
        remplace, equivalentes = self.references_liees(reference)
        details_profile = profil.get('details_profile') or None

        resultat = self.generateur.generer(
            profil, resultat_titre['titre'], HtmlExportService.generate_html_brands(appareils),
            reference, remplace, equivalentes,
            lambda reste: HtmlExportService.generate_html_details(
                appareils, profile_name=details_profile, char_limit=reste),
        )
        QApplication.clipboard().setText(resultat['html'])
        self._signaler(profil, donnees, ref_obsolete, appareils, remplace, equivalentes, resultat)

    # ─── Références liées ────────────────────────────────────────────────────

    def references_liees(self, reference: str) -> Tuple[List[str], List[List[str]]]:
        """
        (anciennes références de `reference`, lignées équivalentes).

        Une lignée équivalente = [équivalente, ses anciennes références…] ; une
        ancienne version dont la remplaçante est hors du groupe a donc sa propre
        lignée. Lignées classées par nombre d'appareils décroissant, à égalité
        par ordre alphabétique. Chaque référence n'apparaît qu'une fois.
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
            except Exception:
                anciennes = []
            lignee = [equivalente] + [r for r in anciennes if r not in deja and r != equivalente]
            deja.update(lignee)
            lignees.append(lignee)

        # Même décompte que les métas (appareils distincts de toute la lignée)
        seo = self.main_window.seo_service
        nb = {lignee[0]: seo._count_compatible_models(lignee) for lignee in lignees}
        lignees.sort(key=lambda l: (-nb[l[0]], l[0]))
        return remplace, lignees

    # ─── Compte rendu ────────────────────────────────────────────────────────

    def _signaler(self, profil, donnees, ref_obsolete, appareils, remplace, equivalentes,
                  resultat) -> None:
        reference = donnees['reference']
        nb_marques = len({r[1].strip() for r in appareils if len(r) > 1 and r[1] and r[1].strip()})
        resume = (f"{len(appareils)} appareil{'s' if len(appareils) > 1 else ''}, "
                  f"{nb_marques} marque{'s' if nb_marques > 1 else ''}")
        status = f"Fiche copiée ({resultat['longueur']} car., {resume})"
        if ref_obsolete:
            status += f" [Supersédée → {reference}]"

        detail = f"Fiche: '{reference}'"
        if ref_obsolete:
            detail += f" (remplace {ref_obsolete})"
        detail += f" — profil « {profil.get('name', '')} »"
        detail += f"\n==> {resume} ; {resultat['longueur']} car."
        if remplace:
            detail += f"\n==> Remplace : {' '.join(remplace)}"
        for lignee in equivalentes:
            detail += f"\n==> Équivalente : {' '.join(lignee)}"
        strategie = HtmlExportService.last_strategy_used
        if "Données trop volumineuses" in resultat['html']:
            detail += "\n==> [!] Limite de caractères dépassée : liste des appareils remplacée par un avertissement"
        elif strategie == 'ref_modele':
            detail += "\n==> Limite de caractères atteinte : références modèle uniquement"
        elif strategie == 'commercial_ref':
            detail += "\n==> Limite de caractères atteinte : références commerciales uniquement"

        self.main_window.user_interaction_service.add_to_history(detail)
        self.main_window.statusbar.showMessage(status, 4000)
