"""
Champ « Réf. associée » de la fenêtre d'import (CDC docs/cdc_import_fiches_site.md,
§ 10.17) : pour une pièce Whirlpool, Indesit ou Beko, la référence jumelle dans
l'un des deux autres groupes, ou « aucune ».

Le champ ne s'affiche que si la référence de la pièce a la forme de l'un de ces
groupes (table des formats). Il se préremplit avec la réponse mémorisée, sinon
avec l'équivalente de code produit d'une fiche reprise, ou la 2ᵉ réf. du code
produit d'une fiche en cours d'import. Sans réponse, rien n'est mémorisé et la
question reviendra au prochain import.
"""

from typing import Callable, Optional, Tuple

from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget

from src.utils.rapprochement_fiche.associee import autres_origines, origine_associable
from .ref_chips_input import RefChipsInput
from .style_manager import StyleManager

# (réponse connue, référence associée ou None) pour une réf. de pièce
Memoire = Callable[[str], Tuple[bool, Optional[str]]]


class ChampReferenceAssociee(QWidget):
    """Réf. associée d'une pièce : une référence, ou « aucune »."""

    def __init__(self, memoire: Optional[Memoire] = None, proposee: str = '',
                 largeur_libelle: int = 0, parent=None):
        super().__init__(parent)
        self._memoire = memoire
        self._proposee = proposee or ''
        self._reference = ''
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(6)
        self.libelle = QLabel("Réf. associée :")
        self.libelle.setStyleSheet(StyleManager.TEXTE_GRAS_TRANSPARENT if largeur_libelle
                                   else StyleManager.LIBELLE_PETIT_TRANSPARENT)
        if largeur_libelle:
            self.libelle.setFixedWidth(largeur_libelle)
        disposition.addWidget(self.libelle)
        self.champ = RefChipsInput("Référence jumelle (ex : C00319033)", max_refs=1)
        disposition.addWidget(self.champ, 1)
        self.aucune = QCheckBox("aucune")
        self.aucune.setToolTip("Cette pièce n'a pas de référence associée : la question "
                               "ne sera plus posée.")
        self.aucune.toggled.connect(self._sur_aucune)
        disposition.addWidget(self.aucune)
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
        self.libelle.setText("Réf. associée :")
        self.libelle.setToolTip(f"Référence jumelle {autres_origines(origine)} de cette pièce "
                                f"{origine}, ou « aucune ».")
        self.champ.definir_aide(f"Réf. {autres_origines(origine)} (ex : C00319033)")
        connue, associee = (self._memoire(reference) if self._memoire is not None
                            else (False, None))
        self.aucune.blockSignals(True)
        self.aucune.setChecked(connue and not associee)
        self.aucune.blockSignals(False)
        self.champ.setEnabled(not self.aucune.isChecked())
        self.champ.set_refs([associee or self._proposee] if (associee or self._proposee) else [])

    def _sur_aucune(self, coche: bool):
        if coche:
            self.champ.set_refs([])
        self.champ.setEnabled(not coche)

    # --- Réponse --------------------------------------------------------------------
    @property
    def reference(self) -> str:
        return self._reference

    def reponse(self) -> Tuple[bool, Optional[str]]:
        """(répondu, référence associée ou None pour « aucune »). Pièce hors des trois
        groupes, ou champ laissé vide : pas de réponse."""
        if not origine_associable(self._reference):
            return False, None
        if self.aucune.isChecked():
            return True, None
        refs = self.champ.refs()
        return (True, refs[0]) if refs else (False, None)
