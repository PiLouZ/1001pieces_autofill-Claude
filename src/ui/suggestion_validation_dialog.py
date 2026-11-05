"""Fenêtre « Valider les suggestions » Type/Marque (refonte v3.94.0).

Gabarit commun `FenetreRevue` : état ✓/✗/· par appareil, lignes regroupées par
preuve (même référence, référence voisine, type de la pièce, famille de préfixe),
puces à compteur, panneau de détail (preuve, vote des pièces de l'appareil, autres
candidats à « prendre », risques), raccourcis V/R/U.

Décisions remises à la fenêtre principale :
    on_validate(decisions) : [(db_id, candidat retenu)] — chemin batché et historisé ;
    on_refuse(refusees)    : [(db_id, [candidats])] — mémorisées, plus proposées.

Les suggestions sûres (candidat unique, preuve forte) arrivent déjà validées ;
toutes les autres en attente.

Non bloquant : ouvert via show() + callbacks (jamais exec_(), cf. conventions projet).
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

from src.core.config import pluralize
from src.services.reference_similarity_service import (
    LIBELLE_PREUVE, ORDRE_PREUVE, est_autre_ref, est_type_piece, est_type_seul, pourcent,
    risques_suggestion, texte_preuve,
)
from .fenetre_revue import (
    FenetreRevue, VALIDE, ATTENTE, COL_ETAT, entree as entree_de, html,
    lignes_vote, phrase_abstention, verdict_pieces as verdict_pieces_champ,
)
from .tri_colonnes import ROLE_TRI

# ── Colonnes ────────────────────────────────────────────────────────────────
COL_REF = 1
COL_NEW_TYPE = 2
COL_NEW_MFR = 3
COL_PREUVE = 4
COL_RISQUE = 5

_ROLE_CAND = Qt.UserRole + 40      # candidat retenu (dict)
_ROLE_EDITED = Qt.UserRole + 41    # valeur saisie à la main

# Palier technique → libellé de fiabilité (conservé pour l'historique et les tests)
_TIER_LABEL = {
    'A_suffix_variant': "Quasi-certain",
    'B_fuzzy_alpha': "Probable",
    'B_fuzzy_numeric': "Probable",
    'C_prefix_consensus': "À vérifier",
    'P_type_piece': "Type de la pièce",
    'P_autre_ref': "Autre référence",
}


def tier_label(tier):
    return _TIER_LABEL.get(tier, "Probable")


def score_color(score):
    """Couleur du % de score, liée au score : vert fort, ambre moyen, ROUGE faible."""
    if score >= 0.90:
        return QColor("#2e7d32")
    if score >= 0.86:
        return QColor("#b06a00")
    return QColor("#c0392b")


def fiability_colors(score):
    """(fond, texte) liés au score — ROUGE quand le score est faible."""
    if score >= 0.90:
        return ("#E8F5E9", "#2e7d32")
    if score >= 0.86:
        return ("#FFF8E1", "#b06a00")
    return ("#FDECEA", "#c0392b")


def is_safe_default(entry):
    """Arrive validée : candidat unique ET (palier A OU score ≥ 0,90)."""
    cands = entry.get('candidates') or []
    if len(cands) != 1:
        return False
    c = cands[0]
    return c.get('confidence_tier') == 'A_suffix_variant' or float(c.get('score', 0)) >= 0.90


def _tier(entry):
    cands = entry.get('candidates') or []
    return cands[0].get('confidence_tier') if cands else None


def verdict_pieces(proposition, preuves):
    """Verdict des pièces de l'appareil sur le Type proposé (cf. fenetre_revue)."""
    return verdict_pieces_champ(proposition.get('type'), preuves, 'type')


class SuggestionValidationDialog(FenetreRevue):
    TITRE = "Valider les suggestions Type / Marque"
    ENTETES = ["Référence", "Type", "Marque", "Preuve", "⚠"]
    LARGEURS = {COL_NEW_TYPE: 150, COL_NEW_MFR: 130, COL_PREUVE: 104, COL_RISQUE: 30}
    COL_ETIREE = COL_REF
    MODES_GROUPE = [('preuve', "Preuve"), ('marque', "Marque proposée"),
                    ('voisin', "Appareil voisin"), ('aucun', "Aucun")]
    LIBELLE_APPLIQUER = "Appliquer"
    NOM_LIGNE = 'suggestion'

    def __init__(self, parent, snapshot, on_validate, value_picker=None,
                 on_refuse=None, preuves=None):
        """value_picker(db_field, current_value, candidates, sur_resultat) : ouvre la
        fenêtre Cmd+D (non bloquante) et appelle sur_resultat(str|dict) à la
        validation. preuves(entrée) -> {'nb_pieces', 'paires'} : vote des pièces
        de l'appareil, lu à la consultation de la ligne. Tous deux optionnels."""
        self._on_validate = on_validate
        self._on_refuse = on_refuse
        self._value_picker = value_picker
        super().__init__(parent, snapshot, preuves=preuves)

    # ── Spécialisation du gabarit ────────────────────────────────────────────
    def _etat_initial(self, entree):
        return VALIDE if is_safe_default(entree) else ATTENTE

    def _remplir_feuille(self, item, entree):
        ref = entree.get('ref_modele') or ''
        comm = entree.get('commercial_ref') or ''
        texte = ref if not comm else f"{ref}  ·  {comm}"
        item.setText(COL_REF, texte)
        item.setToolTip(COL_REF, texte)
        cands = entree.get('candidates') or []
        if cands:
            self._poser_candidat(item, cands[0])
        risques = risques_suggestion(cands)
        item.setText(COL_RISQUE, "⚠" if risques else "")
        item.setForeground(COL_RISQUE, QBrush(QColor("#fd7e14")))
        item.setTextAlignment(COL_RISQUE, Qt.AlignCenter)
        item.setToolTip(COL_RISQUE, "\n".join(risques))
        item.setData(COL_RISQUE, ROLE_TRI, len(risques))

    def _poser_candidat(self, item, cand):
        item.setData(COL_ETAT, _ROLE_CAND, cand)
        item.setData(COL_ETAT, _ROLE_EDITED, False)
        for col, champ in ((COL_NEW_TYPE, 'type'), (COL_NEW_MFR, 'manufacturer')):
            item.setText(col, cand.get(champ, '') or '')
            item.setBackground(col, QBrush())
        if not (cand.get('manufacturer') or '').strip():
            item.setText(COL_NEW_MFR, "")
            item.setToolTip(COL_NEW_MFR, "Type seul : la marque reste à saisir")
        item.setText(COL_PREUVE, texte_preuve(cand))
        item.setData(COL_PREUVE, ROLE_TRI, (ORDRE_PREUVE.get(cand.get('confidence_tier'), 1),
                                            -float(cand.get('score', 0) or 0)))
        tier = cand.get('confidence_tier')
        couleur = "#2e7d32" if tier == 'A_suffix_variant' else (
            "#b06a00" if tier == 'C_prefix_consensus' else "#343a40")
        item.setForeground(COL_PREUVE, QBrush(QColor(couleur)))

    def _memoriser_correction(self, item):
        return (item.data(COL_ETAT, _ROLE_CAND), bool(item.data(COL_ETAT, _ROLE_EDITED)),
                item.text(COL_NEW_TYPE), item.text(COL_NEW_MFR))

    def _reprendre_correction(self, memo, item):
        cand, edite, type_v, marque_v = memo
        if cand is not None:
            self._poser_candidat(item, cand)
        if edite:
            item.setText(COL_NEW_TYPE, type_v)
            item.setText(COL_NEW_MFR, marque_v)
            self._marquer_modifiee(item)

    def _cle_groupe(self, entree, mode):
        cands = entree.get('candidates') or []
        meilleur = cands[0] if cands else {}
        if mode == 'preuve':
            tier = meilleur.get('confidence_tier')
            return (ORDRE_PREUVE.get(tier, 1), LIBELLE_PREUVE.get(tier, "Autre"))
        if mode == 'marque':
            return (0, meilleur.get('manufacturer') or "(type seul, sans marque)")
        if mode == 'voisin':
            if est_type_piece(meilleur):
                return (1, f"Pièce {meilleur.get('ref', '')}")
            if est_autre_ref(meilleur):
                return (1, f"Autre réf. « {meilleur.get('ref', '')} »")
            return (0, meilleur.get('ref') or "—")
        return None

    def _puces(self):
        puces = []
        for tier, libelle in (('A_suffix_variant', "Même réf."), ('B', "Réf. voisine"),
                              ('P_type_piece', "Pièce"), ('P_autre_ref', "Autre réf."),
                              ('C_prefix_consensus', "Préfixe")):
            if tier == 'B':
                pred = lambda e: (_tier(e) or '').startswith('B_')
            else:
                pred = (lambda t: lambda e: _tier(e) == t)(tier)
            puces.append((tier, libelle, pred))
        puces.append(('risque', "⚠ À risque",
                      lambda e: bool(risques_suggestion(e.get('candidates') or []))))
        return puces

    def _texte_recherche(self, item):
        cand = item.data(COL_ETAT, _ROLE_CAND) or {}
        return " ".join([item.text(COL_REF), item.text(COL_NEW_TYPE), item.text(COL_NEW_MFR),
                         cand.get('ref', '') or ''])

    def _reference(self, item):
        entree = entree_de(item)
        return (entree or {}).get('ref_modele') or (entree or {}).get('commercial_ref') or ''

    def _cle_preuves(self, entree):
        return entree.get('db_id')

    # ── Panneau de détail ────────────────────────────────────────────────────
    def _html_detail(self, item, preuves):
        entree = entree_de(item) or {}
        cands = entree.get('candidates') or []
        retenu = item.data(COL_ETAT, _ROLE_CAND) or (cands[0] if cands else {})
        refs = " · ".join(r for r in (entree.get('ref_modele'), entree.get('commercial_ref')) if r)
        propose = " / ".join(v for v in (item.text(COL_NEW_TYPE), item.text(COL_NEW_MFR)) if v)
        parties = [f"<h3 style='margin:0'>{html(refs)}</h3>",
                   f"<p style='margin:4px 0 8px 0'>Proposé : <b>{html(propose) or '—'}</b>"]
        if item.data(COL_ETAT, _ROLE_EDITED):
            parties.append(" <span style='color:#0d6efd'>(corrigé à la main)</span>")
        actuel = " / ".join(v for v in (entree.get('current_type'), entree.get('current_manufacturer')) if v)
        if actuel:
            parties.append(f"<br><span style='color:#6c757d'>Déjà en base : {html(actuel)}</span>")
        parties.append("</p>")

        parties.append("<p style='margin:0'><b>Preuve</b></p><p style='margin:2px 0 8px 0'>")
        parties.append(self._phrase_preuve(retenu))
        parties.append("</p>")

        parties.append("<p style='margin:0'><b>Pièces de l'appareil</b></p><p style='margin:2px 0 8px 0'>")
        parties.append(self._phrase_pieces(retenu, preuves))
        parties.append("</p>")

        autres = [(i, c) for i, c in enumerate(cands) if c != retenu]
        if autres:
            parties.append("<p style='margin:0'><b>Autres candidats</b></p><ul style='margin:2px 0 8px 0'>")
            for i, c in autres:
                libelle = " / ".join(v for v in (c.get('type'), c.get('manufacturer')) if v)
                parties.append(f"<li>{html(libelle)} <span style='color:#6c757d'>"
                               f"({html(texte_preuve(c))})</span> — "
                               f"<a href='prendre:{i}'>Prendre</a></li>")
            parties.append("</ul>")

        risques = risques_suggestion(cands)
        verdict = verdict_pieces(retenu, preuves)[0]
        if verdict == 'contredit':
            risques = risques + ["les pièces de l'appareil désignent un autre type"]
        if risques:
            parties.append("<p style='margin:0;color:#b45309'><b>⚠ À regarder</b></p>"
                           "<ul style='margin:2px 0 0 0;color:#b45309'>")
            parties.extend(f"<li>{html(r)}</li>" for r in risques)
            parties.append("</ul>")
        return "".join(parties)

    @staticmethod
    def _phrase_preuve(cand):
        tier = cand.get('confidence_tier')
        ref = html(cand.get('ref', ''))
        score = float(cand.get('score', 0) or 0)
        if tier == 'A_suffix_variant':
            return f"Même appareil que <b>{ref}</b>, à un suffixe de variante près."
        if tier == 'C_prefix_consensus':
            if cand.get('nb_famille'):
                return (f"Famille de références <b>{html(cand.get('prefixe', ''))}…</b> : "
                        f"{cand['nb_accord']} appareils sur {cand['nb_famille']} sont "
                        f"« {html(cand.get('type'))} / {html(cand.get('manufacturer'))} » "
                        f"(ex. {ref}). Aucun appareil identique.")
            return f"Famille de préfixe dominée par cette marque (ex. {ref})."
        if est_type_piece(cand):
            n = int(cand.get('nb_appareils') or 0)
            return (f"{round(score * n)} des {n} appareils typés de la pièce <b>{ref}</b> "
                    f"sont de type « {html(cand.get('type'))} ». Marque à saisir.")
        if est_autre_ref(cand):
            n = int(cand.get('nb_appareils') or 0)
            return (f"{round(score * n)} des {n} appareils typés dont l'autre référence est "
                    f"« <b>{ref}</b> » sont de type « {html(cand.get('type'))} ». "
                    f"Indice du fichier fournisseur, pas une certitude. Marque à saisir.")
        return f"Référence voisine <b>{ref}</b> — ressemblance {pourcent(score)}."

    @staticmethod
    def _phrase_pieces(cand, preuves):
        if preuves is None:
            return "<span style='color:#6c757d'>Non lues.</span>"
        if not preuves.get('nb_pieces'):
            return "<span style='color:#6c757d'>Aucune pièce associée : pas de contre-preuve.</span>"
        verdict, type_top, part, total = verdict_pieces(cand, preuves)
        debut = f"{pluralize(preuves['nb_pieces'], 'pièce')}. "
        if not total:
            return debut + "<span style='color:#6c757d'>Aucun autre appareil typé ne les partage.</span>"
        lignes = lignes_vote(preuves)
        if verdict == 'confirme':
            constat = f"<span style='color:#198754'>Confirment le type ({pourcent(part)} « {html(type_top)} »).</span>"
        elif verdict == 'contredit':
            constat = (f"<span style='color:#dc3545'>Contredisent : {pourcent(part)} des appareils "
                       f"qui les partagent sont « {html(type_top)} ».</span>")
        else:
            constat = (f"<span style='color:#6c757d'>"
                       f"{phrase_abstention(part, total).capitalize()}.</span>")
        return f"{debut}{constat}<br><span style='color:#6c757d'>{lignes}</span>"

    def _on_lien(self, cible, item):
        if not cible.startswith('prendre:') or item is None:
            return
        entree = entree_de(item) or {}
        cands = entree.get('candidates') or []
        try:
            cand = cands[int(cible.split(':', 1)[1])]
        except (ValueError, IndexError):
            return
        self._poser_candidat(item, cand)
        self._apres_correction(item)

    # ── Correction (fenêtre Cmd+D) ───────────────────────────────────────────
    def _corriger(self, item, colonne=None):
        """Choisir un candidat (dict) remplit Type ET Marque ; une valeur libre (str)
        ne touche que la colonne corrigée (Type par défaut, au clavier)."""
        if self._value_picker is None:
            return
        colonne = colonne if colonne in (COL_NEW_TYPE, COL_NEW_MFR) else (
            COL_NEW_TYPE if colonne is None else None)
        if colonne is None:
            return
        champ = 'type' if colonne == COL_NEW_TYPE else 'manufacturer'
        cands = (entree_de(item) or {}).get('candidates') or []

        def _sur_resultat(resultat):
            if resultat is None:
                return
            if isinstance(resultat, dict):
                self._poser_candidat(item, resultat)
            else:
                item.setText(colonne, resultat)
                self._marquer_modifiee(item)
            self._apres_correction(item)

        self._value_picker(champ, item.text(colonne), cands, _sur_resultat)

    def _marquer_modifiee(self, item):
        item.setData(COL_ETAT, _ROLE_EDITED, True)
        item.setText(COL_PREUVE, "corrigé")
        item.setForeground(COL_PREUVE, QBrush(QColor("#0d6efd")))
        item.setBackground(COL_NEW_TYPE, QBrush(QColor("#E3F2FD")))
        item.setBackground(COL_NEW_MFR, QBrush(QColor("#E3F2FD")))

    # ── Décisions ────────────────────────────────────────────────────────────
    def collecter_decisions(self, items):
        """[(db_id, candidat retenu)] des lignes validées ayant une valeur à écrire."""
        decisions = []
        for item in items:
            entree = entree_de(item) or {}
            db_id = entree.get('db_id')
            type_v = (item.text(COL_NEW_TYPE) or '').strip()
            mfr_v = (item.text(COL_NEW_MFR) or '').strip()
            if db_id is None or (not type_v and not mfr_v):
                continue
            retenu = item.data(COL_ETAT, _ROLE_CAND) or {}
            cand = {'type': type_v, 'manufacturer': mfr_v, 'ref': retenu.get('ref', '') or '',
                    'score': retenu.get('score', 0) or 0}
            if est_type_seul(retenu):
                cand.update(confidence_tier=retenu['confidence_tier'],
                            nb_appareils=retenu.get('nb_appareils'))
            if item.data(COL_ETAT, _ROLE_EDITED):
                cand['ref'] = (cand['ref'] + " · ajusté").strip(' ·')
            decisions.append((db_id, cand))
        return decisions

    def _appliquer(self, valides, refuses):
        decisions = self.collecter_decisions(valides)
        if decisions and callable(self._on_validate):
            self._on_validate(decisions)
        refusees = [((entree_de(it) or {}).get('db_id'),
                     (entree_de(it) or {}).get('candidates') or [])
                    for it in refuses]
        refusees = [(db_id, cands) for db_id, cands in refusees if db_id is not None]
        if refusees and callable(self._on_refuse):
            self._on_refuse(refusees)
