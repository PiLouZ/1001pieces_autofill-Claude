"""
Champ « Réf. associée » de la fenêtre d'import (CDC docs/cdc_import_fiches_site.md,
§ 10.17) : pour une pièce Whirlpool, Indesit ou Beko, la référence jumelle dans
l'un des deux autres groupes, à droite de la référence de la pièce. Facultative.

Le champ ne s'affiche que si la référence de la pièce a la forme de l'un de ces
groupes (table des formats). Il se préremplit avec la réponse mémorisée, sinon
avec l'équivalente de code produit d'une fiche reprise, ou la 2ᵉ réf. du code
produit d'une fiche en cours d'import. Laissée vide, rien n'est retenu.
"""

from typing import Callable, Optional, Tuple

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.utils.rapprochement_fiche.associee import autres_origines, origine_associable
from .ref_chips_input import RefChipsInput
from .style_manager import StyleManager

# (réponse connue, référence associée ou None) pour une réf. de pièce
Memoire = Callable[[str], Tuple[bool, Optional[str]]]


class ChampReferenceAssociee(QWidget):
    """Réf. associée d'une pièce, à droite de sa référence : facultative, elle ne
    bloque rien ; laissée vide, rien n'est retenu."""

    def __init__(self, memoire: Optional[Memoire] = None, proposee: str = '',
                 largeur: int = 260, petit: bool = False, parent=None):
        super().__init__(parent)
        self._memoire = memoire
        self._proposee = proposee or ''
        self._reference = ''
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(6)
        self.libelle = QLabel("Réf. associée :")
        self.libelle.setStyleSheet(StyleManager.LIBELLE_PETIT_TRANSPARENT if petit
                                   else StyleManager.TEXTE_GRAS_TRANSPARENT)
        disposition.addWidget(self.libelle)
        self.champ = RefChipsInput("Réf. jumelle", max_refs=1)
        self.champ.setFixedWidth(largeur)
        disposition.addWidget(self.champ)
        self.setVisible(False)

    # --- Référence de la pièce ------------------------------------------------------
    def definir_reference(self, reference: str):
        """La référence de la pièce change (fichier, ou saisie d'un collage) : le
        champ s'affiche si elle est Whirlpool, Indesit ou Beko, et se préremplit."""
        reference = (reference or '').strip()
        if reference == self._reference:
            return
        self._reference = reference
        origine = origine_associable(reference)
        self.setVisible(bool(origine))
        if not origine:
            return
        self.libelle.setToolTip(f"Référence jumelle {autres_origines(origine)} de cette pièce "
                                f"{origine}. Facultative : laissée vide, rien n'est retenu.")
        self.champ.definir_aide(f"Réf. {autres_origines(origine)}")
        _, associee = (self._memoire(reference) if self._memoire is not None else (False, None))
        valeur = associee or self._proposee
        self.champ.set_refs([valeur] if valeur else [])

    # --- Réponse --------------------------------------------------------------------
    @property
    def reference(self) -> str:
        return self._reference

    def reponse(self) -> Tuple[bool, Optional[str]]:
        """(répondu, référence associée). Pièce hors des trois groupes, ou champ
        laissé vide : pas de réponse."""
        if not origine_associable(self._reference):
            return False, None
        refs = self.champ.refs()
        return (True, refs[0]) if refs else (False, None)
