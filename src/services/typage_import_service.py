"""
Typage des appareils importés par les règles de nomenclature (CDC § 8.3, lot 5).

Pour chaque ligne importée (PDF, CSV, collage, fiche du site — un seul point
d'entrée : `ImportManager._parse_row_data`) :

- **type vide, ou auto-complété par référence** : la règle validée qui
  s'applique donne le type ; il est noté comme une auto-complétion (source
  « règle de nomenclature … ») et l'appareil passe « à vérifier ». Une règle
  validée l'emporte sur l'auto-complétion par référence, qui recopie un
  appareil dont rien ne garantit le type (D17) ;
- **type lu dans le fichier, contredit par une règle** : le type du fichier est
  gardé (l'import n'écrase jamais) ; l'appareil reçoit une **proposition de
  type** (fenêtre « Types proposés », lot 4) en fin d'import (D18) ;
- **type du fichier hors de la liste fermée** (`types_autorises`) : gardé,
  signalé au récapitulatif, non bloquant (D19).

Seules les règles **validées** s'appliquent (§ 6.2, D4) : mesuré au lot 5, les
règles découvertes d'office (D7 ≥ 98 %) auraient typé 526 appareils sur 929
contre le choix final de l'utilisateur (Bosch HMG* surtout).

L'index des règles est construit une fois par import (`charger`), pas par ligne.
Un refus mémorisé (`refus_completions`, champ 'type') n'est jamais réécrit : le
circuit des auto-complétions de l'import le filtre déjà sur un appareil existant,
et le calcul des propositions l'écarte.
"""

from typing import Any, Dict, Iterable, Optional

from ..core.constants import TypesAppareils
from ..core.logger import app_logger
from ..utils.nomenclature.cles import cle_code, cle_nom
from ..utils.nomenclature.moteur import IndexRegles, Regle, Resolution, STATUT_VALIDEE
from ..utils.types_autorises import est_type_autorise
from .base_service import BaseService

# Source d'une auto-complétion posée par une règle (appareils_autocompletes.source)
PREFIXE_SOURCE_REGLE = "règle de nomenclature "


def source_de_regle(regle: Regle) -> str:
    """« règle de nomenclature Gaggenau BS* → Four vapeur »."""
    from .regle_nomenclature_service import libelle_regle
    return PREFIXE_SOURCE_REGLE + libelle_regle(
        {'portee': regle.portee, 'cible': regle.cible, 'motif': regle.motif,
         'type_resultat': regle.type_resultat})


def est_source_de_regle(source: Optional[str]) -> bool:
    return (source or '').startswith(PREFIXE_SOURCE_REGLE)


class TypageImportService(BaseService):
    """Règles validées appliquées aux lignes d'un import, et ce qu'il en reste à dire."""

    # Verdicts de `examiner`
    RIEN = 'rien'
    TYPER = 'typer'            # type vide ou auto-complété : la règle le donne
    CONTREDIT = 'contredit'    # type du fichier ≠ règle : proposition en fin d'import

    def __init__(self, db_manager, parent_window=None):
        super().__init__(parent_window)
        self.db_manager = db_manager
        self._regles_service = None
        self._index: Optional[IndexRegles] = None
        self._types_autorises = ()
        self.reinitialiser()

    # ── Session d'import ─────────────────────────────────────────────────────

    def reinitialiser(self) -> None:
        """Constats d'une session d'import, par identité d'appareil (une ligne vue
        deux fois — doublon, ou les deux passages du chemin batch — compte une fois)."""
        self.typees: Dict[str, str] = {}            # clé → type donné par une règle
        self.contredites: Dict[str, Dict[str, Any]] = {}   # clé → device_data
        self.hors_liste: Dict[str, str] = {}        # clé → type du fichier hors liste
        self.ids_typees = set()                     # appareils réellement typés (tracés)

    def _service_regles(self):
        if self._regles_service is None:
            from .regle_nomenclature_service import RegleNomenclatureService
            self._regles_service = RegleNomenclatureService(self.db_manager)
        return self._regles_service

    def charger(self) -> bool:
        """Construire l'index des règles validées (une fois par import).
        Échec : typage désactivé pour cet import, journalisé, jamais bloquant."""
        self._index = None
        try:
            service = self._service_regles()
            validees = [r for r in service.regles() if r.statut == STATUT_VALIDEE]
            self._index = IndexRegles(validees, service.groupe_de)
            self._types_autorises = service.types_autorises
            return True
        except Exception as e:
            app_logger.warning(f"[Import] Règles de nomenclature indisponibles "
                               f"(typage par règle désactivé) : {e}")
            self._index = None
            self._types_autorises = ()
            return False

    def _index_pret(self) -> Optional[IndexRegles]:
        """Index chargé (à la demande hors import : _try_auto_complete et les aperçus)."""
        if self._index is None:
            self.charger()
        return self._index

    # ── Une ligne ────────────────────────────────────────────────────────────

    def resoudre(self, marque: str, ref_modele: str, commercial_ref: str) -> Resolution:
        index = self._index_pret()
        if index is None or not (marque or '').strip():
            return Resolution()
        return index.resoudre(marque, cle_nom(ref_modele, commercial_ref),
                              cle_code(ref_modele, commercial_ref))

    def examiner(self, device_data: Dict[str, Any], type_auto_complete: bool):
        """(verdict, résolution) pour une ligne déjà parsée et auto-complétée.

        Args:
            type_auto_complete: le type présent vient de l'auto-complétion par
                référence (et non du fichier).
        """
        type_ligne = (device_data.get('type') or '').strip()
        if type_ligne in TypesAppareils.ACCESSOIRES:   # D9 : jamais retypé
            return self.RIEN, None
        resolution = self.resoudre(device_data.get('manufacturer') or '',
                                   device_data.get('ref_modele') or '',
                                   device_data.get('commercial_ref') or '')
        if not resolution.type or resolution.type == type_ligne:
            return self.RIEN, resolution
        if not type_ligne or type_auto_complete:
            return self.TYPER, resolution
        return self.CONTREDIT, resolution

    def est_hors_liste(self, type_appareil: str) -> bool:
        """Type absent de la liste fermée (liste illisible : rien n'est signalé)."""
        if self._index_pret() is None or not self._types_autorises:
            return False
        return bool(type_appareil) and not est_type_autorise(type_appareil, self._types_autorises)

    # ── Fin d'import ─────────────────────────────────────────────────────────

    def proposer_pour_contredits(self) -> int:
        """Propositions de type pour les appareils dont le fichier contredit une
        règle (D18), calculées et rangées comme au recalcul (force, signaux,
        refus écartés) ; les autres propositions restent. Returns : nombre rangé."""
        ids = [d.get('id') for d in self.contredites.values() if d.get('id')]
        if not ids:
            return 0
        try:
            bilan = self._service_regles().calculer_propositions(ecrire=True, appareil_ids=ids)
        except Exception as e:
            app_logger.warning(f"[Import] Propositions de type non calculées : {e}")
            return 0
        if not bilan.ecrit:
            return 0
        return len(bilan.propositions)

    @staticmethod
    def lignes_hors_liste(compteur: Iterable) -> str:
        """« Cocotte (12), Filte charbon (3) »."""
        return ", ".join(f"{t} ({n})" for t, n in compteur)
