"""Fenêtre « Auto-complétés à vérifier » (refonte v3.94.0).

Liste les appareils dont un Type ou un Fabricant a été écrit par l'auto-complétion
d'un import. Gabarit commun `FenetreRevue` : état ✓/✗/· par appareil (✓ d'office :
une auto-complétion est présumée juste), lignes regroupées par import, appareil
source ou confiance, puces à compteur, panneau de détail (valeur écrite et sa
source, ce que disent les pièces de l'appareil), raccourcis V/R/U.

Décisions remises à la fenêtre principale :
    on_validate(verifies, corrections) : ids vérifiés (traces retirées) et
        [(id, {champ: valeur})] des seuls champs corrigés ;
    on_refuse(refus) : [(id, {champ: valeur auto-complétée})] — champs à vider,
        refus mémorisé pour que l'import ne les réécrive pas.

Non bloquant : ouvert via show() + callbacks (jamais exec_(), cf. conventions projet).
"""

from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush, QFont

from src.core.config import pluralize
from .fenetre_revue import (
    FenetreRevue, VALIDE, COL_ETAT, entree as entree_de, ROLE_MODIFIEE, html, verdict_pieces,
    lignes_vote, phrase_abstention,
)
from .tri_colonnes import ROLE_TRI

# ── Colonnes ────────────────────────────────────────────────────────────────
COL_REF = 1
COL_TYPE = 2
COL_MFR = 3
COL_CONFIANCE = 4
COL_SOURCE = 5
COL_IMPORT = 6

_CHAMP_PAR_COLONNE = {COL_TYPE: 'type', COL_MFR: 'manufacturer'}
_NOM_CHAMP = {'type': "Type", 'manufacturer': "Marque"}
_LE_CHAMP = {'type': "le type", 'manufacturer': "la marque"}

_ROLE_ORIGINAL = Qt.UserRole + 40   # {champ: valeur actuelle en base}


def regrouper_traces(lignes):
    """Lignes de `lire_autocompletions_a_verifier` → une entrée par appareil.

    Returns:
        [{'id', 'ref_modele', 'commercial_ref', 'type', 'manufacturer',
          'champs': {champ: {'valeur', 'source', 'accord', 'total'}},
          'import_ts'}], triées du moins sûr au plus sûr (cf. cle_de_tri).
    """
    par_id = {}
    for (appareil_id, ref_modele, commercial_ref, type_actuel, fabricant_actuel,
         champ, valeur, source, accord, total, import_ts) in lignes or []:
        entree = par_id.setdefault(appareil_id, {
            'id': appareil_id, 'ref_modele': ref_modele or '',
            'commercial_ref': commercial_ref or '', 'type': type_actuel or '',
            'manufacturer': fabricant_actuel or '', 'champs': {}, 'import_ts': import_ts,
        })
        entree['champs'][champ] = {'valeur': valeur, 'source': source or '',
                                   'accord': accord, 'total': total}
        entree['import_ts'] = max(entree['import_ts'] or '', import_ts or '')
    return sorted(par_id.values(), key=cle_de_tri)


def confiance(entree):
    """(accord, total) du champ le moins sûr de l'appareil ; (None, None) si une
    source ne dit rien de sa représentativité (cache du chemin batch)."""
    pire = None
    for p in entree['champs'].values():
        if p['accord'] is None or not p['total']:
            return (None, None)
        if pire is None or (p['accord'] / p['total'], p['total']) < (pire[0] / pire[1], pire[1]):
            pire = (p['accord'], p['total'])
    return pire or (None, None)


def cle_de_tri(entree):
    """Inconnue d'abord, puis par accord croissant, puis par nombre de sources
    croissant (« 1/1 » est moins sûr que « 12/12 »), puis import le plus récent."""
    accord, total = confiance(entree)
    import_ts = entree.get('import_ts') or ''
    recence = tuple(-ord(c) for c in import_ts)
    if accord is None:
        return (0, 0, 0, recence)
    return (1, accord / total, total, recence)


# Catégories de confiance : (clé, libellé de puce, libellé de groupe), du moins
# sûr au plus sûr
_CATEGORIES = (('inconnue', "Inconnue", "Confiance inconnue"),
               ('partagee', "Partagées", "Sources partagées"),
               ('unique', "Source unique", "Une seule source"),
               ('unanime', "Unanimes", "Sources unanimes (2 ou plus)"))


def categorie(entree):
    """Clé de catégorie de confiance de l'appareil (cf. _CATEGORIES)."""
    accord, total = confiance(entree)
    if accord is None:
        return 'inconnue'
    if accord < total:
        return 'partagee'
    return 'unique' if total == 1 else 'unanime'


def couleur_confiance(accord, total):
    """Vert : unanimité sur au moins 2 sources. Ambre : une seule source, ou
    majorité nette. Rouge : sources partagées ou confiance inconnue."""
    if accord is None:
        return QColor("#c0392b")
    if accord == total and total >= 2:
        return QColor("#2e7d32")
    if accord == total or accord / total >= 0.75:
        return QColor("#b06a00")
    return QColor("#c0392b")


def libelle_confiance(accord, total):
    if accord is None:
        return "?"
    return f"{accord}/{total}"


def date_lisible(import_ts):
    try:
        return datetime.fromisoformat(import_ts).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return import_ts or ''


class AutocompletionReviewDialog(FenetreRevue):
    TITRE = "Auto-complétés à vérifier"
    ENTETES = ["Référence", "Type", "Marque", "Confiance", "Source", "Import"]
    COL_ETIREE = COL_REF
    MODES_GROUPE = [('import', "Import"), ('source', "Appareil source"),
                    ('confiance', "Confiance"), ('aucun', "Aucun")]
    LIBELLE_APPLIQUER = "Appliquer"
    NOM_LIGNE = 'appareil'

    def __init__(self, parent, entrees, on_validate, value_picker=None,
                 on_refuse=None, preuves=None):
        """value_picker(db_field, current_value, candidates) -> str|dict|None : la
        fenêtre Cmd+D. preuves(entrée) -> {'nb_pieces', 'paires'} : vote des
        pièces de l'appareil. Tous deux optionnels (tests sans service)."""
        self._on_validate = on_validate
        self._on_refuse = on_refuse
        self._value_picker = value_picker
        super().__init__(parent, entrees, preuves=preuves)
        largeur_date = self._arbre.fontMetrics().horizontalAdvance("00/00/0000 00:00") + 24
        for col, largeur in ((COL_TYPE, 125), (COL_MFR, 105), (COL_CONFIANCE, 86),
                             (COL_SOURCE, 100), (COL_IMPORT, largeur_date)):
            self._arbre.setColumnWidth(col, largeur)

    # ── Spécialisation du gabarit ────────────────────────────────────────────
    def _etat_initial(self, entree):
        # Une auto-complétion est présumée juste (demande utilisateur, v3.89.1)
        return VALIDE

    def _remplir_feuille(self, item, entree):
        italique = QFont()
        italique.setItalic(True)
        refs = " - ".join(r for r in (entree['ref_modele'], entree['commercial_ref']) if r)
        item.setText(COL_REF, refs or f"#{entree['id']}")
        item.setData(COL_ETAT, _ROLE_ORIGINAL,
                     {'type': entree['type'], 'manufacturer': entree['manufacturer']})
        for col, champ in _CHAMP_PAR_COLONNE.items():
            item.setText(col, entree[champ])
            prov = entree['champs'].get(champ)
            if prov:
                item.setFont(col, italique)
                item.setToolTip(col, (
                    f"Auto-complété d'après {prov['source'] or '?'} "
                    f"({libelle_confiance(prov['accord'], prov['total'])})"))
            else:
                item.setForeground(col, QBrush(QColor("#9e9e9e")))
        accord, total = confiance(entree)
        item.setText(COL_CONFIANCE, libelle_confiance(accord, total))
        item.setData(COL_CONFIANCE, ROLE_TRI, cle_de_tri(entree)[:3])
        item.setForeground(COL_CONFIANCE, QBrush(couleur_confiance(accord, total)))
        item.setTextAlignment(COL_CONFIANCE, Qt.AlignCenter)
        if accord is None:
            item.setToolTip(COL_CONFIANCE, "Une seule source connue, représentativité inconnue")
        sources = sorted({p['source'] for p in entree['champs'].values() if p['source']})
        item.setText(COL_SOURCE, ", ".join(sources))
        item.setText(COL_IMPORT, date_lisible(entree.get('import_ts')))
        item.setData(COL_IMPORT, ROLE_TRI, entree.get('import_ts') or '')

    def _memoriser_correction(self, item):
        return {col: item.text(col) for col in _CHAMP_PAR_COLONNE}

    def _reprendre_correction(self, memo, item):
        for col, valeur in memo.items():
            if valeur != item.text(col):
                self._poser_valeur(item, col, valeur)

    def _cle_groupe(self, entree, mode):
        if mode == 'import':
            ts = entree.get('import_ts') or ''
            return (tuple(-ord(c) for c in ts), f"Import du {date_lisible(ts)}" if ts else "Import inconnu")
        if mode == 'source':
            sources = sorted({p['source'] for p in entree['champs'].values() if p['source']})
            return (0, ", ".join(sources) or "Source inconnue")
        if mode == 'confiance':
            cle = categorie(entree)
            ordre = [c[0] for c in _CATEGORIES].index(cle)
            return (ordre, _CATEGORIES[ordre][2])
        return None

    def _puces(self):
        return [(cle, libelle, (lambda c: lambda e: categorie(e) == c)(cle))
                for cle, libelle, _ in _CATEGORIES]

    def _reference(self, item):
        entree = entree_de(item) or {}
        return entree.get('ref_modele') or entree.get('commercial_ref') or ''

    def _cle_preuves(self, entree):
        return entree.get('id')

    # ── Panneau de détail ────────────────────────────────────────────────────
    def _html_detail(self, item, preuves):
        entree = entree_de(item) or {}
        refs = " · ".join(r for r in (entree.get('ref_modele'), entree.get('commercial_ref')) if r)
        parties = [f"<h3 style='margin:0'>{html(refs)}</h3>"]
        parties.append("<p style='margin:6px 0 0 0'><b>Valeurs écrites par l'import</b></p>"
                       "<ul style='margin:2px 0 8px 0'>")
        for champ in ('type', 'manufacturer'):
            prov = entree.get('champs', {}).get(champ)
            if not prov:
                continue
            accord, total = prov['accord'], prov['total']
            confiance_txt = ("représentativité inconnue" if accord is None else
                             f"{accord} source{'s' if accord > 1 else ''} d'accord sur {total}")
            parties.append(f"<li>{_NOM_CHAMP[champ]} : <i>{html(prov['valeur'])}</i> "
                           f"(le champ était vide) — d'après <b>{html(prov['source']) or '?'}</b>, "
                           f"{confiance_txt}.</li>")
        parties.append("</ul>")
        parties.append("<p style='margin:0'><b>Pièces de l'appareil</b></p><p style='margin:2px 0 8px 0'>")
        parties.append(self._phrase_pieces(item, preuves))
        parties.append("</p>")
        if categorie(entree) != 'unanime':
            parties.append("<p style='margin:0;color:#b45309'><b>⚠ À regarder</b> : "
                           f"{dict((c[0], c[2]) for c in _CATEGORIES)[categorie(entree)].lower()}.</p>")
        parties.append("<p style='color:#6c757d;margin-top:8px'>Refuser vide les champs "
                       "auto-complétés ; l'import ne les réécrira plus pour cet appareil.</p>")
        return "".join(parties)

    def _phrase_pieces(self, item, preuves):
        if preuves is None:
            return "<span style='color:#6c757d'>Non lues.</span>"
        if not preuves.get('nb_pieces'):
            return "<span style='color:#6c757d'>Aucune pièce associée : pas de contre-preuve.</span>"
        lignes = [f"{pluralize(preuves['nb_pieces'], 'pièce')}."]
        for col, champ in _CHAMP_PAR_COLONNE.items():
            verdict, top, part, total = verdict_pieces(item.text(col), preuves, champ)
            if not total:
                continue
            nom = _LE_CHAMP[champ]
            if verdict == 'confirme':
                lignes.append(f"<span style='color:#198754'>Confirment {nom} "
                              f"({round(part * 100)} % « {html(top)} »).</span>")
            elif verdict == 'contredit':
                lignes.append(f"<span style='color:#dc3545'>Contredisent {nom} : "
                              f"{round(part * 100)} % sont « {html(top)} ».</span>")
            else:
                lignes.append(f"<span style='color:#6c757d'>{_NOM_CHAMP[champ]} : "
                              f"{phrase_abstention(part, total)}.</span>")
        vote = lignes_vote(preuves)
        if vote:
            lignes.append(f"<span style='color:#6c757d'>{vote}</span>")
        return "<br>".join(lignes)

    # ── Correction (fenêtre Cmd+D) ───────────────────────────────────────────
    def _corriger(self, item, colonne=None):
        colonne = COL_TYPE if colonne is None else colonne
        champ = _CHAMP_PAR_COLONNE.get(colonne)
        if self._value_picker is None or champ is None:
            return False
        resultat = self._value_picker(champ, item.text(colonne), [])
        if isinstance(resultat, dict):
            resultat = resultat.get(champ) or ''
        resultat = (resultat or '').strip()
        if not resultat:
            return False
        self._poser_valeur(item, colonne, resultat)
        return True

    def _poser_valeur(self, item, colonne, valeur):
        champ = _CHAMP_PAR_COLONNE[colonne]
        item.setText(colonne, valeur)
        original = (item.data(COL_ETAT, _ROLE_ORIGINAL) or {}).get(champ, '')
        item.setBackground(colonne, QBrush(QColor("#E3F2FD")) if valeur != original else QBrush())
        if valeur != original:
            item.setData(COL_ETAT, ROLE_MODIFIEE, True)

    # ── Décisions ────────────────────────────────────────────────────────────
    def collecter_decisions(self, items=None):
        """(verifies, corrections) des lignes validées — cf. docstring du module."""
        items = [it for it in self._feuilles if self.etat(it) == VALIDE] if items is None else items
        verifies, corrections = [], []
        for item in items:
            entree = entree_de(item) or {}
            original = item.data(COL_ETAT, _ROLE_ORIGINAL) or {}
            verifies.append(entree['id'])
            champs = {champ: item.text(col).strip()
                      for col, champ in _CHAMP_PAR_COLONNE.items()
                      if item.text(col).strip() and item.text(col).strip() != original.get(champ, '')}
            if champs:
                corrections.append((entree['id'], champs))
        return verifies, corrections

    @staticmethod
    def collecter_refus(items):
        """[(id, {champ: valeur auto-complétée})] : les champs encore égaux à la
        valeur écrite par l'import (un champ déjà modifié n'est plus le sien)."""
        refus = []
        for item in items:
            entree = entree_de(item) or {}
            champs = {champ: prov['valeur'] for champ, prov in entree.get('champs', {}).items()
                      if (entree.get(champ) or '').strip().lower()
                      == (prov['valeur'] or '').strip().lower()}
            if champs:
                refus.append((entree['id'], champs))
        return refus

    def _appliquer(self, valides, refuses):
        verifies, corrections = self.collecter_decisions(valides)
        if verifies and callable(self._on_validate):
            self._on_validate(verifies, corrections)
        refus = self.collecter_refus(refuses)
        if refus and callable(self._on_refuse):
            self._on_refuse(refus)
