"""
Modèles de lecture tirés des profils « Fiche » de la configuration (CDC § 4.2)

Les gabarits d'export servent aussi de modèles de lecture : le texte qui
entoure {reference} / {references} devient le repère. Un profil Fiche ne porte
que les lignes de références ; la liste des appareils (titre, en-tête de
marque, ligne d'appareil) vient de SON profil HTML Détails (details_profile,
vide = profil Détails par défaut). Un modèle réunit donc les deux.

Si un gabarit change, l'export et la lecture suivent ensemble : il n'y a pas
de réglage de lecture séparé. Sans Qt ni base : la configuration est passée
en dictionnaire (celle d'ExportConfigService).
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from src.utils.lecteur_fiche.normalisation import Bloc, nettoyer_texte, normaliser

_MARQUEUR = 'ZZREPEREZZ'


def cle_texte(texte: str) -> str:
    """Forme de comparaison d'un libellé : minuscules, sans « : » ni espaces de bord."""
    return nettoyer_texte(texte).rstrip(' :').casefold()


@dataclass(frozen=True)
class Repere:
    """Bloc attendu : balise, classes, et texte avant/après la valeur."""
    balise: str
    classes: FrozenSet[str]
    prefixe: str          # texte avant la valeur, ex. « Code produit : »
    suffixe: str = ''

    def valeur(self, bloc: Bloc) -> Optional[str]:
        """Texte de la valeur si `bloc` correspond au repère, sinon None."""
        if not bloc.a_les_classes(self.classes):
            return None
        texte = bloc.texte
        pref = self.prefixe.rstrip()
        if not texte.casefold().startswith(pref.casefold()):
            return None
        reste = texte[len(pref):]
        suff = self.suffixe.strip()
        if suff and reste.casefold().rstrip().endswith(suff.casefold()):
            reste = reste.rstrip()[:-len(suff)]
        return reste.strip()


@dataclass(frozen=True)
class ModeleLecture:
    """Repères d'un profil Fiche (+ son profil HTML Détails)."""
    nom: str
    code_produit: Optional[Repere]
    remplace: Optional[Repere]
    equivalentes: Optional[Repere]
    separateur_references: str = ' '
    titres_liste: Tuple[str, ...] = ()       # libellés avant la liste (cle_texte)
    classes_liste: FrozenSet[str] = frozenset()  # classes englobant la liste
    entete_marque: Optional[Repere] = None
    marque_par_id: bool = False              # l'en-tête de marque porte id="{marque}"
    inclure_informations: bool = False
    max_caracteres: int = 0
    profil_details: str = ''
    titre_litteraux: Tuple[str, ...] = ()    # textes fixes du gabarit Titre (cle_texte)
    profil_titre: str = ''

    def signature(self) -> tuple:
        """Deux profils de même signature se lisent exactement de la même façon."""
        return (self.code_produit, self.remplace, self.equivalentes,
                self.separateur_references, self.titres_liste, self.classes_liste,
                self.entete_marque, self.marque_par_id, self.inclure_informations,
                self.titre_litteraux)


def _repere(gabarit: str, variables: Tuple[str, ...]) -> Optional[Repere]:
    """Repère du bloc qui contient la variable ; None si gabarit vide ou sans variable."""
    if not gabarit:
        return None
    texte = gabarit
    trouve = False
    for v in variables:
        if v in texte:
            texte = texte.replace(v, _MARQUEUR)
            trouve = True
    if not trouve:
        return None
    for bloc in normaliser(texte):
        if _MARQUEUR in bloc.texte:
            avant, _, apres = bloc.texte.partition(_MARQUEUR)
            return Repere(bloc.balise, bloc.classes, avant, apres.replace(_MARQUEUR, ''))
    return None


def _liste(wrapper: str) -> Tuple[Tuple[str, ...], FrozenSet[str]]:
    """Libellés placés avant {appareils} et classes qui englobent la liste."""
    if not wrapper or '{appareils}' not in wrapper:
        return (), frozenset()
    titres: List[str] = []
    classes: FrozenSet[str] = frozenset()
    for bloc in normaliser(wrapper.replace('{appareils}', _MARQUEUR)):
        if _MARQUEUR in bloc.texte:
            classes = bloc.classes_parents | bloc.classes
            break
        if bloc.texte:
            titres.append(cle_texte(bloc.texte))
    return tuple(titres), classes


def _litteraux_titre(template: str) -> Tuple[str, ...]:
    """Textes fixes d'un gabarit Titre (« pour », « (photos non contractuelles) »…)."""
    morceaux = re.split(r'\{[a-z_]+\}', template or '')
    textes = (cle_texte(' '.join(b.texte for b in normaliser(m))) if '<' in m
              else cle_texte(m) for m in morceaux)
    return tuple(t for t in textes if len(t) >= 3)


def _profil_titre(config: Dict[str, Any], nom: str) -> Dict[str, Any]:
    titre_cfg = config.get('titre') or {}
    profils = titre_cfg.get('profiles') or []
    nom = nom or titre_cfg.get('default_profile') or ''
    for p in profils:
        if p.get('name') == nom:
            return p
    return profils[0] if profils else {}


def _profil_details(config: Dict[str, Any], nom: str) -> Dict[str, Any]:
    html_cfg = config.get('html') or {}
    profils = html_cfg.get('details_profiles') or []
    nom = nom or html_cfg.get('details_default_profile') or ''
    for p in profils:
        if p.get('name') == nom:
            return p
    if profils:
        return profils[0]
    return html_cfg.get('details') or {}


def modele_depuis_profil(profil: Dict[str, Any], config: Dict[str, Any]) -> ModeleLecture:
    """Modèle de lecture d'un profil Fiche, avec le profil Détails qu'il désigne."""
    details = _profil_details(config, profil.get('details_profile') or '')
    titre = _profil_titre(config, profil.get('titre_profile') or '')
    titres, classes_liste = _liste(details.get('wrapper_template') or '')
    entete = _repere(details.get('brand_header_template') or '', ('{marque}',))
    try:
        max_car = max(0, int(profil.get('max_caracteres') or 0))
    except (TypeError, ValueError):
        max_car = 0
    return ModeleLecture(
        nom=str(profil.get('name') or ''),
        code_produit=_repere(profil.get('code_produit_template') or '',
                             ('{reference}', '{references}')),
        remplace=_repere(profil.get('remplace_template') or '', ('{references}',)),
        equivalentes=_repere(profil.get('equivalentes_template') or '', ('{references}',)),
        separateur_references=profil.get('separateur_references') or ' ',
        titres_liste=titres,
        classes_liste=classes_liste,
        entete_marque=entete,
        marque_par_id='id="{marque}"' in (details.get('brand_header_template') or ''),
        inclure_informations=bool(profil.get('inclure_informations')),
        max_caracteres=max_car,
        profil_details=str(details.get('name') or ''),
        titre_litteraux=_litteraux_titre(titre.get('template') or ''),
        profil_titre=str(titre.get('name') or ''),
    )


def modeles_depuis_config(config: Dict[str, Any]) -> List[ModeleLecture]:
    """Un modèle par profil Fiche enregistré (dans l'ordre de la configuration)."""
    profils = ((config or {}).get('fiche') or {}).get('profiles') or []
    return [modele_depuis_profil(p, config) for p in profils if isinstance(p, dict)]
