"""
Assemblage d'une fiche produit complète (bouton « Fiche complète »)

Ordre des blocs : titre, marques, code produit, « Remplace les références »,
« Références équivalentes », bloc Informations (facultatif), liste des
appareils. Les lignes de références sans référence ne sont pas écrites.

Code produit : {reference} vaut la référence, suivie de la 2ᵉ réf. du code
produit quand la fiche du site en avait une (paire Whirlpool / Indesit…).
Équivalentes : sans `lignes_equivalentes`, toutes les lignées sur une seule
ligne ; avec, une ligne « Références équivalentes » par liste (une par marque
d'origine, cf. FicheProduitService.references_fiche).

Sans Qt ni base : les blocs déjà rendus (titre, marques) et la liste des
appareils (fonction de la limite restante) sont fournis par l'appelant.
"""

import html
from typing import Any, Callable, Dict, List, Optional

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
               remplace: List[str], equivalentes: List[List[str]],
               code_produit: Optional[List[str]] = None,
               lignes_equivalentes: Optional[List[List[str]]] = None) -> str:
        """Tout ce qui précède la liste des appareils."""
        separateur = profil.get('separateur_references', " ")
        code = [r for r in (code_produit or [reference]) if r]
        if lignes_equivalentes is None:
            # Toutes les lignées équivalentes à la suite, dans leur ordre, sur une ligne
            lignes_equivalentes = [[ref for lignee in equivalentes for ref in lignee]]
        modele_equivalentes = profil.get('equivalentes_template', "")
        blocs = [
            titre or "",
            marques_html or "",
            (profil.get('code_produit_template', "")
             .replace('{reference}',
                      separateur.join(html.escape(r, quote=True) for r in code))),
            self.ligne_references(profil.get('remplace_template', ""), remplace, separateur),
            *(self.ligne_references(modele_equivalentes, ligne, separateur)
              for ligne in lignes_equivalentes),
        ]
        if profil.get('inclure_informations'):
            blocs.append(profil.get('informations_template', ""))
        return "".join(blocs)

    def generer(self, profil: Dict[str, Any], titre: str, marques_html: str, reference: str,
                remplace: List[str], equivalentes: List[List[str]],
                appareils_fn: Callable[[int], str],
                code_produit: Optional[List[str]] = None,
                lignes_equivalentes: Optional[List[List[str]]] = None) -> Dict[str, Any]:
        """
        Fiche complète. `appareils_fn(limite)` rend la liste des appareils en
        tenant dans `limite` caractères visibles (None = limite de son profil) :
        la limite de la fiche (max_caracteres, 0 = celle du profil HTML Détails)
        porte sur la fiche ENTIÈRE, donc la liste reçoit ce que l'en-tête laisse.
        """
        debut = self.entete(profil, titre, marques_html, reference, remplace, equivalentes,
                            code_produit, lignes_equivalentes)
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
