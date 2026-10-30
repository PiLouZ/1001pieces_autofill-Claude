"""
Assemblage d'une fiche produit complète (bouton « Fiche complète »)

Ordre des blocs : titre, marques, code produit, « Remplace les références »,
une ligne par référence équivalente, bloc Informations (facultatif), liste
des appareils. Les lignes de références sans référence ne sont pas écrites.

Sans Qt ni base : les blocs déjà rendus (titre, marques) et la liste des
appareils (fonction de la limite restante) sont fournis par l'appelant.
"""

import html
from typing import Any, Callable, Dict, List

from src.services.html_export_service import HtmlExportService


class FicheProduitGenerator:
    """Assemble le HTML d'une fiche selon un profil de la section « fiche »."""

    @staticmethod
    def ligne_references(template: str, references: List[str], separateur: str) -> str:
        """Ligne `template` avec {references} jointes ; '' sans référence."""
        refs = [r for r in (references or []) if r]
        if not refs or not template:
            return ""
        return template.replace('{references}',
                                separateur.join(html.escape(r, quote=True) for r in refs))

    def entete(self, profil: Dict[str, Any], titre: str, marques_html: str, reference: str,
               remplace: List[str], equivalentes: List[List[str]]) -> str:
        """Tout ce qui précède la liste des appareils."""
        separateur = profil.get('separateur_references', " ")
        blocs = [
            titre or "",
            marques_html or "",
            (profil.get('code_produit_template', "")
             .replace('{reference}', html.escape(reference or "", quote=True))),
            self.ligne_references(profil.get('remplace_template', ""), remplace, separateur),
        ]
        blocs += [self.ligne_references(profil.get('equivalentes_template', ""), lignee, separateur)
                  for lignee in equivalentes]
        if profil.get('inclure_informations'):
            blocs.append(profil.get('informations_template', ""))
        return "".join(blocs)

    def generer(self, profil: Dict[str, Any], titre: str, marques_html: str, reference: str,
                remplace: List[str], equivalentes: List[List[str]],
                appareils_fn: Callable[[int], str]) -> Dict[str, Any]:
        """
        Fiche complète. `appareils_fn(limite)` rend la liste des appareils en
        tenant dans `limite` caractères visibles (None = limite de son profil) :
        la limite de la fiche (max_caracteres, 0 = celle du profil HTML Détails)
        porte sur la fiche ENTIÈRE, donc la liste reçoit ce que l'en-tête laisse.
        """
        debut = self.entete(profil, titre, marques_html, reference, remplace, equivalentes)
        limite = int(profil.get('max_caracteres', 0) or 0)
        reste = None
        if limite:
            reste = max(0, limite - HtmlExportService.count_non_html_chars(debut))
        fiche = debut + (appareils_fn(reste) or "")
        return {
            'html': fiche,
            'longueur': HtmlExportService.count_non_html_chars(fiche),
            'limite': limite,
        }
