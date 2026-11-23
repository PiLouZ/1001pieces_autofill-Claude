"""Branchement des règles de nomenclature dans la fenêtre principale (lot 4).

- barre d'état : « ▲ Types proposés (N) ▼ » — flèches du critère
  « type_propose » de `TableController._CRITERES_NAV` (même circuit que les
  lignes à vérifier, PR #150), le bouton ouvre la revue ;
- tableau : cellule Type teintée (vert d'eau) et bulle « Type proposé : … » ;
  clic droit « Accepter / Refuser le type proposé » ;
- menu Données → « Règles de nomenclature… » : l'écran des règles ;
- décisions : `RevuePropositionsService` (sauvegarde événementielle,
  historique, refus mémorisés), puis relecture de la page affichée.

Tout passe par des fenêtres non bloquantes (show() + callbacks).
"""

from typing import Iterable, List, Optional

import qtawesome as qta
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction, QHBoxLayout, QMessageBox, QPushButton, QWidget

from src.core.config import pluralize
from src.core.logger import app_logger
from src.services.revue_propositions_service import (
    RevuePropositionsService, groupable, libelle_proposition_regle)
from .style_manager import StyleManager


class RevueNomenclature:
    """Glue entre la fenêtre principale, le tableau et les fenêtres du lot 4."""

    def __init__(self, main_window):
        self.main = main_window
        self.service = RevuePropositionsService(main_window.db_manager, main_window)
        self.groupe = None
        self.bouton = None
        self._regles_dialog = None
        self._revue_dialog = None
        self._confirmation = None

    # ── Barre d'état ─────────────────────────────────────────────────────────
    def creer_groupe_barre_etat(self):
        """« ▲ Types proposés (N) ▼ », masqué tant que N = 0."""
        from .incomplete_nav_widget import creer_fleche_nav
        self.groupe = QWidget()
        cadre = QHBoxLayout(self.groupe)
        cadre.setContentsMargins(0, 0, 0, 0)
        cadre.setSpacing(2)
        fleches = [creer_fleche_nav(
            self.main, direction, QKeySequence(touche), libelle,
            "Type proposé par une règle de nomenclature, pas encore écrit", 'type_propose')
            for direction, touche, libelle in (
                ('up', "Ctrl+Alt+Shift+PgUp", "Type proposé précédent"),
                ('down', "Ctrl+Alt+Shift+PgDown", "Type proposé suivant"))]
        self.bouton = QPushButton()
        self.bouton.setIcon(qta.icon('fa5s.tags', color='white'))
        self.bouton.setStyleSheet(StyleManager.TYPES_PROPOSES_BTN)
        self.bouton.setToolTip("Types proposés par les règles de nomenclature validées, pas "
                               "encore écrits.\nClic : fenêtre de revue. Clic droit sur une "
                               "cellule Type teintée : accepter ou refuser.")
        self.bouton.clicked.connect(lambda: self.ouvrir_revue())
        cadre.addWidget(fleches[0])
        cadre.addWidget(self.bouton)
        cadre.addWidget(fleches[1])
        controleur = getattr(self.main, 'table_controller', None)
        if controleur is not None:
            controleur.set_type_propose_nav_buttons(*fleches)
        self.groupe.setVisible(False)
        return self.groupe

    def rafraichir(self):
        """Relire les propositions : teinte des cellules, flèches, compteur."""
        par_appareil = self.service.propositions_par_appareil()
        controleur = getattr(self.main, 'table_controller', None)
        model = getattr(controleur, 'model', None)
        if model is not None and hasattr(model, 'set_propositions_type'):
            model.set_propositions_type({
                i: {'type': p['type_propose'], 'regle': libelle_proposition_regle(p),
                    'force': p.get('force') or ''}
                for i, p in par_appareil.items()})
            controleur.on_propositions_type_changed()
        n = len(par_appareil)
        if self.bouton is not None:
            self.bouton.setText(f"Types proposés ({n})")
        if self.groupe is not None:
            self.groupe.setVisible(n > 0)
        if self._regles_dialog is not None and self._regles_dialog.isVisible():
            self._regles_dialog.recharger()
        return n

    # ── Écran des règles ─────────────────────────────────────────────────────
    def ouvrir_regles(self):
        from .regles_nomenclature_dialog import ReglesNomenclatureDialog
        if self._regles_dialog is None:
            self._regles_dialog = ReglesNomenclatureDialog(
                self.main, self.main.db_manager, self.service,
                on_propositions_changees=self.rafraichir,
                ouvrir_revue=lambda regle_id=None: self.ouvrir_revue(regle_id))
        else:
            self._regles_dialog.recharger()
        self._regles_dialog.show()
        self._regles_dialog.raise_()
        self._regles_dialog.activateWindow()
        return self._regles_dialog

    # ── Revue ────────────────────────────────────────────────────────────────
    def ouvrir_revue(self, regle_id: Optional[int] = None):
        from .propositions_type_dialog import PropositionsTypeDialog
        propositions = self.service.propositions()
        if regle_id is not None:
            propositions = [p for p in propositions if p['regle_id'] == regle_id]
        if not propositions:
            self.rafraichir()
            return None
        if self._revue_dialog is not None and self._revue_dialog.isVisible():
            self._revue_dialog.close()
        # Fortes d'abord (D8), puis par règle
        propositions.sort(key=lambda p: (p.get('force') != 'forte', p['regle_id'] or 0,
                                         p['appareil_id']))
        dialogue = PropositionsTypeDialog(self.main, propositions, self.appliquer,
                                          recapitulatif=self.service.recapitulatif)
        self._revue_dialog = dialogue
        dialogue.show()
        return dialogue

    def appliquer(self, acceptees: List[dict], refusees: List[dict]):
        """Décisions de la revue ou du clic droit : écrire, mémoriser, relire."""
        messages = []
        if acceptees:
            bilan = self.service.accepter(acceptees)
            if bilan.erreur:
                messages.append(f"Types proposés : {bilan.erreur}")
            else:
                texte = (f"Types proposés acceptés : {pluralize(bilan.acceptees, 'appareil')} "
                         f"(règles de nomenclature)")
                if bilan.ignorees:
                    texte += f", {bilan.ignorees} ignoré{'s' if bilan.ignorees > 1 else ''} (type changé depuis)"
                messages.append(texte + ".")
        if acceptees or refusees:
            n = self.service.refuser(refusees) if refusees else 0
            if n:
                messages.append(f"Types proposés refusés : {pluralize(n, 'appareil')} — "
                                f"ils ne seront plus proposés.")
        self._relire_page()
        self.rafraichir()
        interaction = getattr(self.main, 'user_interaction_service', None)
        for message in messages:
            app_logger.info(message)
            if interaction is not None:
                interaction.add_to_history(message)

    def _relire_page(self):
        """Les types écrits apparaissent dans la page affichée (contexte gardé)."""
        db = self.main.db_manager
        try:
            db.invalidate_search_cache(invalidate_total_count=True)
        except Exception as e:
            app_logger.warning(f"[Nomenclature] cache de recherche non invalidé : {e}")
        controleur = getattr(self.main, 'table_controller', None)
        if controleur is not None and hasattr(controleur, '_goto_page_preserving_context'):
            controleur._goto_page_preserving_context(getattr(controleur, 'current_page', 1) or 1)

    # ── Clic droit sur le tableau ────────────────────────────────────────────
    def ajouter_au_menu(self, menu, db_ids: Iterable[int]):
        """Actions « Accepter / Refuser le type proposé » pour les lignes
        sélectionnées qui en portent un."""
        controleur = getattr(self.main, 'table_controller', None)
        model = getattr(controleur, 'model', None)
        if model is None or not hasattr(model, 'ids_types_proposes'):
            return
        ids = model.ids_types_proposes([i for i in db_ids if i is not None])
        if not ids:
            return
        if len(ids) == 1:
            proposition = model.proposition_type_de(ids[0])
            accepter = QAction(f"Accepter le type proposé « {proposition['type']} »", menu)
            refuser = QAction(f"Refuser le type proposé « {proposition['type']} »", menu)
        else:
            accepter = QAction(f"Accepter les types proposés ({len(ids)} appareils)…", menu)
            refuser = QAction(f"Refuser les types proposés ({len(ids)} appareils)", menu)
        accepter.triggered.connect(lambda checked=False, l=list(ids): self.accepter_depuis_tableau(l))
        refuser.triggered.connect(lambda checked=False, l=list(ids): self.refuser_depuis_tableau(l))
        menu.addAction(accepter)
        menu.addAction(refuser)

    def _propositions_de(self, ids):
        par_appareil = self.service.propositions_par_appareil()
        return [par_appareil[i] for i in ids if i in par_appareil]

    def refuser_depuis_tableau(self, ids):
        propositions = self._propositions_de(ids)
        if propositions:
            self.appliquer([], propositions)

    def accepter_depuis_tableau(self, ids):
        """Une ligne : écrite tout de suite (geste explicite sur la cellule).
        Plusieurs : seules les groupables, après le récapitulatif (D8)."""
        propositions = self._propositions_de(ids)
        if len(propositions) <= 1:
            if propositions:
                self.appliquer(propositions, [])
            return
        retenues = [p for p in propositions if groupable(p)]
        ecartees = len(propositions) - len(retenues)
        recap = self.service.recapitulatif(retenues)
        boite = QMessageBox(self.main)
        boite.setIcon(QMessageBox.Question)
        boite.setWindowTitle("Accepter les types proposés")
        boite.setTextFormat(Qt.RichText)
        if not retenues:
            boite.setText("<b>Aucune de ces propositions ne peut être acceptée en groupe.</b>")
            boite.setInformativeText("Propositions simples sans source web : à accepter une "
                                     "par une (D8).")
            boite.addButton("Fermer", QMessageBox.AcceptRole)
        else:
            ecart = "".join(f"<br>{t} : {avant} → {apres}" for t, avant, apres, _ in recap.lignes())
            boite.setText(f"<b>Écrire le type proposé sur {pluralize(recap.nb, 'appareil')} ?</b>")
            boite.setInformativeText(
                (f"{pluralize(ecartees, 'proposition simple', 'propositions simples')} sans source web "
                 f"{'reste' if ecartees == 1 else 'restent'} en attente (une par une).<br>"
                 if ecartees else "") + ecart.lstrip("<br>"))
            boite.addButton("Annuler", QMessageBox.RejectRole)
            ok = boite.addButton("Accepter", QMessageBox.AcceptRole)
            ok.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
            boite.setDefaultButton(ok)
            boite.buttonClicked.connect(lambda b: self.appliquer(retenues, []) if b is ok else None)
        boite.setWindowModality(Qt.WindowModal)
        self._confirmation = boite
        boite.show()
