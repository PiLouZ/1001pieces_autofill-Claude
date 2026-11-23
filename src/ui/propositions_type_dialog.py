"""Fenêtre « Types proposés » — revue des propositions des règles de
nomenclature (CDC docs/cdc_regles_nomenclature.md § 8.2, D8, lot 4).

Gabarit commun `FenetreRevue` : état ✓/✗/· par appareil (en attente d'office :
une proposition n'est jamais écrite sans regard humain, D4), lignes regroupées
par règle, puces Fortes / Simples, panneau de détail (règle et sa source,
signaux : 2e clé, vote des pièces, libellé d'origine).

Décision sur plusieurs lignes à la fois (ligne de groupe, sélection, Espace) :
- refuser : toujours permis ;
- valider : seulement les propositions **groupables** — fortes (D8), ou
  simples d'une règle validée sur source web (lot 4) ; les autres restent en
  attente, une par une, et un bandeau le dit.

« Appliquer » montre d'abord le récapitulatif (nombre d'appareils, comptage
par type avant/après) dès qu'au moins une ligne est acceptée ; la décision
n'est remise à la fenêtre principale qu'après confirmation.

Non bloquant : show() + callbacks (jamais exec_(), cf. conventions projet).
"""

import json

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import QDialog, QLabel, QMessageBox

from src.core.config import pluralize
from src.services.revue_propositions_service import groupable, libelle_proposition_regle
from .fenetre_revue import FenetreRevue, VALIDE, entree as entree_de, html
from .style_manager import StyleManager

COL_REF = 1
COL_MARQUE = 2
COL_ACTUEL = 3
COL_PROPOSE = 4
COL_FORCE = 5
COL_SIGNAUX = 6

_AIDE_GROUPE = ("Validation groupée : propositions fortes, ou simples d'une règle "
                "validée sur une source web. Les autres se valident une par une.")


def signaux_de(proposition) -> dict:
    try:
        return json.loads(proposition.get('signaux') or '{}') or {}
    except (TypeError, ValueError):
        return {}


def resume_signaux(proposition) -> str:
    """« 2 clés · pièces 82 % · libellé » (signaux d'accord seulement)."""
    s = signaux_de(proposition)
    morceaux = []
    if s.get('deux_cles'):
        morceaux.append("2 clés")
    vote = s.get('vote_pieces')
    if vote is not None:
        morceaux.append(f"pièces {round(vote * 100)} %")
    if s.get('libelle'):
        morceaux.append("libellé")
    return " · ".join(morceaux)


def reference_de(proposition) -> str:
    return " - ".join(r for r in (proposition.get('ref_modele') or '',
                                  proposition.get('commercial_ref') or '') if r)


class PropositionsTypeDialog(FenetreRevue):
    TITRE = "Types proposés"
    ENTETES = ["Référence", "Marque", "Type actuel", "Type proposé", "Force", "Signaux"]
    COL_ETIREE = COL_REF
    MODES_GROUPE = [('regle', "Règle"), ('changement', "Changement de type"), ('aucun', "Aucun")]
    LIBELLE_APPLIQUER = "Appliquer"
    NOM_LIGNE = 'proposition'

    def __init__(self, parent, propositions, on_decisions, recapitulatif=None):
        """on_decisions(acceptees, refusees) : listes de propositions (dicts) ;
        recapitulatif(propositions) -> Recapitulatif (service de revue)."""
        self._on_decisions = on_decisions
        self._recapitulatif = recapitulatif
        self._fermer_apres = False
        # Groupes par règle : ceux qui ont des propositions fortes d'abord (D8)
        self._regles_fortes = {p.get('regle_id') for p in propositions if p.get('force') == 'forte'}
        super().__init__(parent, propositions)
        self.setObjectName("propositionsTypeDialog")
        for col, largeur in ((COL_MARQUE, 105), (COL_ACTUEL, 130), (COL_PROPOSE, 150),
                             (COL_FORCE, 64), (COL_SIGNAUX, 150)):
            self._arbre.setColumnWidth(col, largeur)
        # Pas de correction de valeur ici : on accepte ou on refuse le type proposé
        self._btn_corriger.setVisible(False)
        self._bandeau = QLabel()
        self._bandeau.setWordWrap(True)
        self._bandeau.setStyleSheet(StyleManager.BANDEAU_ZONE_GRISE)
        self._bandeau.setVisible(False)
        self.layout().insertWidget(2, self._bandeau)

    # ── Spécialisation du gabarit ────────────────────────────────────────────
    def _remplir_feuille(self, item, p):
        item.setText(COL_REF, reference_de(p) or f"#{p['appareil_id']}")
        item.setText(COL_MARQUE, p.get('manufacturer') or '')
        actuel = p.get('type_en_base') or ''
        item.setText(COL_ACTUEL, actuel)
        if actuel != (p.get('type_actuel') or ''):
            item.setForeground(COL_ACTUEL, QBrush(QColor("#c0392b")))
            item.setToolTip(COL_ACTUEL, "Type changé depuis le calcul : la proposition "
                                        "sera ignorée")
        item.setText(COL_PROPOSE, p['type_propose'])
        police = item.font(COL_PROPOSE)
        police.setBold(True)
        item.setFont(COL_PROPOSE, police)
        forte = p.get('force') == 'forte'
        item.setText(COL_FORCE, "forte" if forte else "simple")
        item.setForeground(COL_FORCE, QBrush(QColor("#198754" if forte else "#6c757d")))
        item.setText(COL_SIGNAUX, resume_signaux(p))
        if groupable(p):
            item.setToolTip(COL_FORCE, _AIDE_GROUPE)

    def _cle_groupe(self, p, mode):
        if mode == 'regle':
            libelle = libelle_proposition_regle(p)
            source = " · source web" if (p.get('source_url') or '').strip() else ""
            rang = 0 if p.get('regle_id') in self._regles_fortes else 1
            return ((rang, libelle.lower()), f"{libelle}{source}")
        if mode == 'changement':
            libelle = f"{p.get('type_actuel') or '(vide)'} → {p['type_propose']}"
            return ((0, libelle.lower()), libelle)
        return None

    def _puces(self):
        return [('fortes', "Fortes", lambda p: p.get('force') == 'forte'),
                ('simples', "Simples", lambda p: p.get('force') != 'forte'),
                ('groupables', "Validation groupée", groupable)]

    def _reference(self, item) -> str:
        p = entree_de(item)
        return (p.get('commercial_ref') or p.get('ref_modele') or '') if p else ''

    def _html_detail(self, item, _preuves) -> str:
        p = entree_de(item)
        s = signaux_de(p)
        lignes = [f"<h3>{html(reference_de(p))}</h3>",
                  f"<p><b>{html(p.get('type_actuel') or '(vide)')}</b> → "
                  f"<b style='color:#138a72'>{html(p['type_propose'])}</b></p>",
                  f"<p>Règle : {html(libelle_proposition_regle(p))}"]
        if (p.get('source_url') or '').strip():
            lignes.append(f" — <a href='{html(p['source_url'])}'>source</a>")
        lignes.append("</p><ul>")
        lignes.append(f"<li>Force : {'forte' if p.get('force') == 'forte' else 'simple'}</li>")
        lignes.append(f"<li>2e clé (code usine) : {'d’accord' if s.get('deux_cles') else '—'}</li>")
        vote = s.get('vote_pieces')
        lignes.append("<li>Vote des pièces : " + (
            f"{round(vote * 100)} % ({s.get('votants', 0)} appareils)" if vote is not None
            else "aucune pièce partagée") + "</li>")
        lignes.append(f"<li>Libellé d'origine : {html(p.get('other_ref') or '—')}"
                      f"{' (d’accord)' if s.get('libelle') else ''}</li></ul>")
        if (p.get('type_en_base') or '') != (p.get('type_actuel') or ''):
            lignes.append("<p style='color:#c0392b'>Type changé depuis le calcul "
                          f"({html(p.get('type_en_base') or '(vide)')}) : la proposition "
                          "sera ignorée.</p>")
        lignes.append(f"<p style='color:#6c757d'>{'Validation groupée possible.' if groupable(p) else 'À valider une par une.'}</p>")
        return "".join(lignes)

    def _on_lien(self, cible, item):
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        if cible.startswith('http'):
            QDesktopServices.openUrl(QUrl(cible))

    # ── Décision groupée bornée (D8 + lot 4) ────────────────────────────────
    def decider(self, etat, cibles=None):
        cibles = self._cibles() if cibles is None else cibles
        if getattr(self, '_bandeau', None) is None:     # pendant la construction
            return super().decider(etat, cibles)
        if etat == VALIDE and len(cibles) > 1:
            retenues = [it for it in cibles if groupable(entree_de(it))]
            ecartees = len(cibles) - len(retenues)
            if ecartees:
                self._bandeau.setText(
                    f"{pluralize(ecartees, 'proposition simple', 'propositions simples')} sans source web "
                    f"{'laissée' if ecartees == 1 else 'laissées'} en attente : "
                    f"{'à valider' if ecartees == 1 else 'à valider une par une'} (D8).")
                self._bandeau.setVisible(True)
            cibles = retenues
            if not cibles:
                return
        else:
            self._bandeau.setVisible(False)
        super().decider(etat, cibles)

    def _on_appliquer(self):
        valides = [entree_de(it) for it in self._feuilles if self.etat(it) == VALIDE]
        if not valides or self._recapitulatif is None:
            super()._on_appliquer()
            return
        recap = self._recapitulatif(valides)
        lignes = "".join(
            f"<tr><td>{html(t)}</td><td align='right'>{avant}</td>"
            f"<td align='right'>{apres}</td>"
            f"<td align='right' style='color:{'#198754' if ecart > 0 else '#c0392b'}'>"
            f"{ecart:+d}</td></tr>" for t, avant, apres, ecart in recap.lignes())
        regles = "<br>".join(f"{html(r)} : {n}" for r, n in recap.par_regle.most_common())
        boite = QMessageBox(self)
        boite.setIcon(QMessageBox.Question)
        boite.setWindowTitle("Accepter les types proposés")
        boite.setTextFormat(Qt.RichText)
        boite.setText(f"<b>Écrire le type proposé sur {pluralize(recap.nb, 'appareil')} ?</b>")
        boite.setInformativeText(
            f"{regles}<br><br><table cellspacing='6'><tr><th align='left'>Type</th>"
            f"<th>Avant</th><th>Après</th><th>Écart</th></tr>{lignes}</table><br>"
            "Chaque règle donne une entrée d'historique, annulable depuis l'écran "
            "« Règles de nomenclature » (onglet Acceptations).")
        fermeture = self._fermer_apres
        self._fermer_apres = False
        abandonner = (boite.addButton("Fermer sans appliquer", QMessageBox.DestructiveRole)
                      if fermeture else None)
        boite.addButton("Annuler", QMessageBox.RejectRole)
        ecrire = boite.addButton("Accepter", QMessageBox.AcceptRole)
        ecrire.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        boite.setDefaultButton(ecrire)

        def _choix(bouton):
            if bouton is ecrire:
                FenetreRevue._on_appliquer(self)
            if fermeture and bouton in (ecrire, abandonner):
                self._fermeture_confirmee = True
                QDialog.reject(self)

        boite.buttonClicked.connect(_choix)
        boite.setWindowModality(Qt.WindowModal)
        self._recap_boite = boite     # référence gardée (show non bloquant)
        boite.show()

    def reject(self):
        """Fermer avec des acceptations en cours : le récapitulatif d'abord
        (le gabarit appliquerait sans le montrer)."""
        if (not self._fermeture_confirmee and self._recapitulatif is not None
                and any(self.etat(it) == VALIDE for it in self._feuilles)):
            self._fermer_apres = True
            self._on_appliquer()
            return
        super().reject()

    def _appliquer(self, valides, refuses):
        self._on_decisions([entree_de(it) for it in valides], [entree_de(it) for it in refuses])
