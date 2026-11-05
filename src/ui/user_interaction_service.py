"""
Service d'interaction utilisateur — v2
Historique structuré avec agrégation cross-appareils, code couleur et barres verticales.

Changements v2 :
- Modèle structuré _history_entries (List[dict]) au lieu de chaînes brutes
- Agrégation : N modifications du même champ → même valeur fusionnées en une entrée ×N
- Barre verticale colorée par type d'action (border-left CSS)
- Séparateurs temporels entre blocs distants de plus de 5 minutes
- API publique add_to_history(message) inchangée — zéro régression
"""

import json
import re
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from ..utils.qt_imports import QMessageBox, QTimer

from src.core.config import Config
from src.core.logger import app_logger


# ── Styles par type d'action ───────────────────────────────────────────────────
# label : badge texte affiché à la place d'une icône emoji (emojis non fiables dans Qt)
# Teintes choisies pour un contraste ≥ 4,5:1 avec le texte blanc du badge (WCAG AA).
# Erreur (rouge vif) et suppression (bordeaux) sont distinctes : un échec ne doit
# pas se confondre avec une suppression voulue.
_ACTION_STYLES: Dict[str, Dict[str, str]] = {
    'edit':   {'color': '#2F6CD0', 'label': 'Modif.'},
    'import': {'color': '#1E7F36', 'label': 'Import'},
    'export': {'color': '#8E44AD', 'label': 'Export'},
    'delete': {'color': '#A33A3A', 'label': 'Suppr.'},
    'error':  {'color': '#D61F1F', 'label': 'Erreur'},
    'undo':   {'color': '#B05E00', 'label': 'Annul.'},
    'piece':  {'color': '#0E7A64', 'label': 'Pièce'},
    'system': {'color': '#6B7778', 'label': 'Système'},
}

# Largeur commune des badges, pour que les titres restent alignés malgré des
# libellés de longueurs différentes (« Pièce » / « Système »).
_BADGE_WIDTH = max(len(s['label']) for s in _ACTION_STYLES.values())

_MAX_HISTORY = 100          # Nombre max d'entrées visibles
_TIME_GAP_MINUTES = 5       # Seuil pour insérer un séparateur temporel

# Mois abrégés en français, indépendants de la locale système
_MOIS_ABREGES = ('janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
                 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.')

# Regex pour parser une ligne "==> Field : 'old' → 'new'"
_RE_ARROW = re.compile(r"==>\s*(.+?)\s*:\s*'(.*)'\s*→\s*'(.*)'")

# Ligne de provenance ajoutée par grouped_history_service, ex. :
#   « (source : suggestion réf. HB978GNM1/K2 (score 100%)) »
_PREFIXE_SOURCE = "(source :"
# Clé d'agrégation : une édition issue d'une suggestion ne se regroupe jamais
# avec une édition manuelle identique (sa provenance serait perdue)
_MARQUE_SOURCE = ("__source__",)
# Plusieurs suggestions regroupées dont la provenance diffère (réf., score)
_SOURCE_REGROUPEE = "(source : suggestions par similarité)"


def _est_ligne_source(ligne: str) -> bool:
    return ligne.strip().startswith(_PREFIXE_SOURCE)


def _separer_source(message: str):
    """(message sans la ligne de provenance, ligne de provenance ou None)."""
    raw = message.replace('\\n', '\n')
    lignes = raw.split('\n')
    sources = [l.strip() for l in lignes if _est_ligne_source(l)]
    if not sources:
        return message, None
    reste = '\n'.join(l for l in lignes if not _est_ligne_source(l))
    return reste, sources[0]


# Regex pour supprimer les emojis du titre (plages Unicode emoji + sélecteurs)
_RE_EMOJI = re.compile(
    '['
    '\U0001F000-\U0001FFFF'   # emoji pictographes
    '\U00002600-\U000027BF'   # symboles divers, dingbats
    '\U0000FE00-\U0000FE0F'   # sélecteurs de variation
    '\U0000200D'              # zero-width joiner
    ']+',
    flags=re.UNICODE
)


def _strip_emoji(text: str) -> str:
    """Supprimer les emojis d'un titre — le badge coloré joue ce rôle."""
    return _RE_EMOJI.sub('', text).strip()



def _detect_action_type(message: str) -> str:
    """Déduire le type d'action à partir du contenu du message."""
    m = message.lower()
    if any(k in m for k in ('[err]', 'erreur', 'error', 'échec')):
        return 'error'
    if any(k in m for k in ('suppression', 'supprimé', 'supprimée')):
        return 'delete'
    if any(k in m for k in ('export csv', 'html marques', 'html détails', 'export html', 'export {')):
        return 'export'
    if 'export' in m and any(k in m for k in ('lignes', 'résultats', 'marques', 'format')):
        return 'export'
    if 'lignes extraites' in m or 'appareils créés' in m or 'appareils :' in m:
        return 'import'
    if 'import' in m and any(k in m for k in ('csv', 'pdf', 'collage', 'créés', 'traités')):
        return 'import'
    if any(k in m for k in ("pièce ajoutée", "pièce modifiée", "pièce supprimée",
                             "pièce '", "association de pièce")):
        return 'piece'
    if any(k in m for k in ('annulation', 'rétabli', 'undo', 'redo', '↩')):
        return 'undo'
    if any(k in m for k in ('duplication', 'glisser-déposer')):
        return 'system'
    if 'sauvegarde' in m or 'seo' in m or 'fts5' in m:
        return 'system'
    if 'modification' in m or '→' in message:
        return 'edit'
    return 'system'


def _parse_single_edit(message: str):
    """
    Tente de parser un message comme une modification simple d'un seul champ.
    Retourne (device_ref, field, old_value, new_value) ou None si non applicable.

    Formats reconnus :
      1. "Modification de l'appareil {ref}\\n     ==> {field} : '{old}' → '{new}'"
      2. "Modification {field}: '{old}' → '{new}'"
    """
    raw = message.replace('\\n', '\n')
    lines = [l.strip() for l in raw.split('\n') if l.strip()]
    if not lines:
        return None

    # Format 1 — grouped_history_service, une seule ligne ==>
    if lines[0].startswith("Modification de l'appareil ") and len(lines) == 2:
        device_ref = lines[0][len("Modification de l'appareil "):]
        m = _RE_ARROW.search(lines[1])
        if m:
            return device_ref.strip(), m.group(1).strip(), m.group(2), m.group(3)

    # Format 2 — appel direct depuis main_refactored, une seule ligne
    if len(lines) == 1:
        m = re.match(r"Modification (.+?):\s*'(.*)'\s*→\s*'(.*)'", lines[0])
        if m:
            return None, m.group(1).strip(), m.group(2), m.group(3)

    return None


def _parse_multi_edit(message: str):
    """
    Tente de parser un message multi-champs généré par grouped_history_service.
    Format : "Modification de l'appareil {ref}\\n ==> F1 : 'old' → 'new'\\n ==> F2 : 'old' → 'new'"

    Retourne (device_ref, [(field, old, new), ...]) ou None si non applicable.
    Nécessite au moins 2 lignes ==> (sinon _parse_single_edit couvre déjà le cas).
    """
    raw = message.replace('\\n', '\n')
    lines = [l.strip() for l in raw.split('\n') if l.strip()]
    if len(lines) < 3:
        return None
    if not lines[0].startswith("Modification de l'appareil "):
        return None

    device_ref = lines[0][len("Modification de l'appareil "):].strip()
    pairs = []
    for line in lines[1:]:
        m = _RE_ARROW.search(line)
        if m:
            pairs.append((m.group(1).strip(), m.group(2), m.group(3)))

    if len(pairs) < 2:
        return None
    return device_ref, pairs


def _parse_entry(message: str, timestamp: datetime) -> Dict[str, Any]:
    """
    Construire un dict d'entrée structurée à partir d'un message brut.

    Champs :
        timestamp      : datetime (pour calculs de séparateur)
        timestamp_str  : "HH:MM:SS"
        action_type    : str
        title          : ligne principale (sans timestamp)
        details        : liste de lignes secondaires (les ==>)
        count          : 1 (sera incrémenté si agrégé)
        devices        : [] ou [ref] si edit simple
        agg_key        : (field, new_value) pour comparaison d'agrégation, ou None
    """
    action_type = _detect_action_type(message)
    raw = message.replace('\\n', '\n')
    lines = [l.strip() for l in raw.split('\n') if l.strip()]

    title = _strip_emoji(lines[0]) if lines else _strip_emoji(message)
    details = lines[1:] if len(lines) > 1 else []

    # Agrégation : edit mono-champ ou multi-champs
    agg_key = None
    devices = []
    if action_type == 'edit':
        # La provenance (suggestion) est une ligne en plus : sans ce retrait, une
        # édition Type + Fabricant n'était plus reconnue comme multi-champs, ou
        # perdait sa provenance — les suggestions acceptées ne laissaient aucune trace.
        message, source = _separer_source(message)
        parsed = _parse_single_edit(message)
        if parsed is not None:
            # Mono-champ : titre concis, pas de details
            device_ref, field, old_val, new_val = parsed
            agg_key = (field, new_val)
            title = f"[{field}]  '{old_val}' → '{new_val}'"
            if device_ref:
                devices = [device_ref]
            details = []  # Infos absorbées dans le titre
        else:
            # Multi-champs : titre groupé, details = les lignes ==>
            multi = _parse_multi_edit(message)
            if multi is not None:
                device_ref, pairs = multi
                # agg_key = ensemble canonique des (champ, nouvelle valeur)
                agg_key = tuple(sorted((f, n) for (f, o, n) in pairs))
                field_names = ' + '.join(f for (f, o, n) in pairs)
                title = f"[{field_names}]"
                if device_ref:
                    devices = [device_ref]
                details = [f"==> {f} : '{o}' → '{n}'" for (f, o, n) in pairs]
        if source:
            details = details + [source]
            if agg_key is not None:
                agg_key = (agg_key, _MARQUE_SOURCE)

    elif action_type == 'export':
        # Exports : "HTML Marques: 7 marques..." → titre "HTML Marques:" + détail "==> 7 marques..."
        first_line = lines[0] if lines else ''
        colon_idx = first_line.find(':')
        if colon_idx != -1:
            title = _strip_emoji(first_line[:colon_idx + 1])
            detail_part = first_line[colon_idx + 1:].strip()
            details = []
            if detail_part:
                details.append(f'==> {detail_part}')
            details.extend(lines[1:])

    return {
        'timestamp': timestamp,
        'timestamp_str': timestamp.strftime('%H:%M:%S'),
        'action_type': action_type,
        'title': title,
        'details': details,
        'count': 1,
        'devices': devices,
        'agg_key': agg_key,
        'duration_ms': None,
    }


def _entree_depuis_base(row: tuple) -> Optional[Dict[str, Any]]:
    """Reconstruire une entrée du panneau depuis une ligne de modifications_history.

    Même structure que _parse_entry, marquée `restauree` : elle ne se regroupe
    jamais avec une entrée de la session en cours, et n'est jamais re-persistée.
    Non conservés en base : durée d'import et lien d'action. Les appareils d'un
    regroupement ×N reviennent tous : chaque modification a sa propre ligne.
    """
    timestamp, action_type, title, details_json, device_ref, field_name, new_value = row
    try:
        ts = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None
    try:
        details = json.loads(details_json) if details_json else []
    except ValueError:
        details = []
    if not isinstance(details, list):
        details = []

    # Clé d'agrégation, reconstruite comme dans _parse_entry
    agg_key = None
    if action_type == 'edit':
        lignes = [d for d in details if not _est_ligne_source(d)]
        if field_name:
            agg_key = (field_name, new_value if new_value is not None else '')
        else:
            paires = [_RE_ARROW.match(d) for d in lignes]
            if paires and all(paires):
                agg_key = tuple(sorted((m.group(1), m.group(3)) for m in paires))
        if agg_key is not None and len(lignes) != len(details):
            agg_key = (agg_key, _MARQUE_SOURCE)

    return {
        'timestamp': ts,
        'timestamp_str': ts.strftime('%H:%M:%S'),
        'action_type': action_type,
        'title': title,
        'details': details,
        'count': 1,
        'devices': [device_ref] if device_ref else [],
        'agg_key': agg_key,
        'duration_ms': None,
        'restauree': True,
    }


def _inserer_entree(entries: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    """Insérer une entrée en tête de liste, ou la regrouper avec la précédente.

    Regroupement : même clé d'agrégation que la dernière entrée (edit identique
    sur plusieurs appareils) → compteur ×N. Une entrée restaurée ne se regroupe
    qu'avec une entrée restaurée : la session en cours reste séparée.
    """
    if (entry['agg_key'] is not None and
            entries and
            entries[0]['agg_key'] == entry['agg_key'] and
            entries[0].get('restauree', False) == entry.get('restauree', False)):
        last = entries[0]
        last['count'] += 1
        # Suggestions regroupées : chaque appareil a sa réf. et son score, l'entrée
        # ×N ne peut en citer qu'une — la dire générique plutôt que trompeuse.
        if last['details'] != entry['details'] and any(_est_ligne_source(d) for d in last['details']):
            last['details'] = [_SOURCE_REGROUPEE if _est_ligne_source(d) else d
                               for d in last['details']]
        if entry['devices']:
            last['devices'].extend(entry['devices'])
        # Mettre à jour le timestamp pour refléter la dernière modification
        last['timestamp'] = entry['timestamp']
        last['timestamp_str'] = entry['timestamp_str']
    else:
        entries.insert(0, entry)
        del entries[_MAX_HISTORY:]


class UserInteractionService:
    """
    Service spécialisé pour les interactions avec l'utilisateur.

    Historique v2 : modèle structuré, agrégation cross-appareils,
    code couleur par type d'action, barres verticales CSS, séparateurs temporels.
    """

    def __init__(self, main_window):
        self.main_window = main_window
        self._history_entries: List[Dict[str, Any]] = []
        # Rendu du panneau différé (> 0) pendant une rafale d'entrées
        self._affichage_differe = 0
        self._affichage_en_retard = False

    # ── Dialogues ──────────────────────────────────────────────────────────────

    def show_error(self, message: str) -> None:
        """Afficher une erreur"""
        QMessageBox.critical(self.main_window, "Erreur", message)

    def show_info(self, message: str) -> None:
        """Afficher une information"""
        QMessageBox.information(self.main_window, "Information", message)

    def show_confirmation(self, title: str, message: str, default_yes: bool = False) -> bool:
        """Afficher une confirmation avec support des raccourcis clavier (Entrée/Échap)"""
        msg_box = QMessageBox(self.main_window)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)

        yes_btn = msg_box.addButton("Oui", QMessageBox.YesRole)
        no_btn = msg_box.addButton("Non", QMessageBox.NoRole)

        if default_yes:
            msg_box.setDefaultButton(yes_btn)
            yes_btn.setDefault(True)
        else:
            msg_box.setDefaultButton(no_btn)
            no_btn.setDefault(True)

        yes_btn.setShortcut("Return")
        no_btn.setShortcut("Escape")

        msg_box.exec_()
        return msg_box.clickedButton() == yes_btn

    def show_save_confirmation(self, title: str, message: str) -> str:
        """Afficher une confirmation Oui/Non/Annuler avec raccourcis clavier"""
        msg_box = QMessageBox(self.main_window)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)

        yes_btn = msg_box.addButton("Oui", QMessageBox.YesRole)
        no_btn = msg_box.addButton("Non", QMessageBox.NoRole)
        cancel_btn = msg_box.addButton("Annuler", QMessageBox.RejectRole)

        msg_box.setDefaultButton(yes_btn)
        yes_btn.setDefault(True)
        yes_btn.setShortcut("Return")
        cancel_btn.setShortcut("Escape")
        no_btn.setShortcut("N")

        msg_box.exec_()
        clicked = msg_box.clickedButton()

        if clicked == yes_btn:
            return "yes"
        elif clicked == no_btn:
            return "no"
        return "cancel"

    # ── Compteur ───────────────────────────────────────────────────────────────

    def update_counter(self) -> None:
        """Mettre à jour le compteur de lignes via TableController"""
        displayed_count = self.main_window.table.rowCount()

        if (hasattr(self.main_window, 'table_controller') and
                hasattr(self.main_window.table_controller, 'size_label') and
                self.main_window.table_controller.size_label):
            # Compteur de la barre de pagination : même rendu que
            # TableController._update_pagination_controls (total du périmètre)
            tc = self.main_window.table_controller
            tc.size_label.setText(tc._format_row_count(tc.total_rows))
        elif hasattr(self.main_window, 'counter_label'):
            if (hasattr(self.main_window, 'total_rows') and
                    self.main_window.use_pagination and
                    self.main_window.total_rows > Config.MAX_DISPLAY_ROWS):
                self.main_window.counter_label.setText(
                    f"Affichées : {displayed_count} / Total : {self.main_window.total_rows:,}")
            else:
                self.main_window.counter_label.setText(f"Lignes : {displayed_count:,}")

    # ── Historique ─────────────────────────────────────────────────────────────

    def add_to_history(self, message: str, duration_ms: Optional[int] = None,
                       lien: Optional[Tuple[str, str]] = None) -> None:
        """
        Ajouter un message à l'historique.
        API identique à v1 — les appelants n'ont pas à changer.

        Args:
            message: Texte brut de l'action (timestamp ajouté automatiquement)
            duration_ms: Durée optionnelle en millisecondes (affichée en gris pour les imports)
            lien: (href, texte) — ligne d'action cliquable sous l'entrée, traitée par
                  MainWindow._handle_history_link. Non persistée : après un
                  redémarrage, l'entrée reste mais sans le lien.

        Logique d'agrégation :
        - Si le nouveau message est un edit mono-champ avec le même (field, new_value)
          que la dernière entrée → incrémenter count et ajouter le device.
        - Sinon → insérer une nouvelle entrée en tête.
        """
        now = datetime.now()
        entry = _parse_entry(message, now)
        if duration_ms is not None:
            entry['duration_ms'] = duration_ms
        if lien is not None:
            entry['lien'] = lien

        # Tentative d'agrégation avec la dernière entrée
        _inserer_entree(self._history_entries, entry)

        self._refresh_display()

        # Persistance inter-sessions (silencieuse si le service n'est pas disponible)
        if hasattr(self.main_window, 'history_service'):
            self.main_window.history_service.persist(entry)

    def restaurer_historique(self) -> None:
        """Recharger dans le panneau les dernières entrées des sessions précédentes.

        Appelé une fois au lancement. Les entrées restaurées passent par le même
        regroupement que les entrées en direct (rejeu chronologique), puis se
        placent SOUS celles de la session déjà présentes. Elles ne sont jamais
        re-persistées : sinon chaque lancement dupliquerait l'historique en base.
        """
        history_service = getattr(self.main_window, 'history_service', None)
        if history_service is None:
            return
        try:
            rows = history_service.get_recent_rows()
        except Exception as e:
            app_logger.warning(f"Historique : rechargement impossible — {e}")
            return

        restaurees: List[Dict[str, Any]] = []
        for row in reversed(rows):  # de la plus ancienne à la plus récente
            entry = _entree_depuis_base(row)
            if entry is not None:
                _inserer_entree(restaurees, entry)

        if not restaurees:
            return
        self._history_entries.extend(restaurees)
        del self._history_entries[_MAX_HISTORY:]
        self._refresh_display()

    @contextmanager
    def differer_affichage(self):
        """Regrouper le rendu du panneau pendant une rafale d'entrées (v3.91.2).

        Chaque `add_to_history` reconstruit le HTML des 100 entrées visibles puis
        le remet en page (`setHtml`, ~15 ms) : 1858 suggestions validées d'un coup
        gelaient l'interface ~30 à 55 s. Les entrées et leur persistance restent
        identiques ; seul le rendu est fait une fois, à la sortie du bloc.
        Réentrant : seul le bloc le plus externe déclenche le rendu.
        """
        self._affichage_differe += 1
        try:
            yield
        finally:
            self._affichage_differe -= 1
            if self._affichage_differe == 0 and self._affichage_en_retard:
                self._affichage_en_retard = False
                self._refresh_display()

    def _refresh_display(self) -> None:
        """Reconstruire et afficher le HTML de l'historique."""
        if self._affichage_differe:
            self._affichage_en_retard = True
            return
        if hasattr(self.main_window, 'history_list'):
            if self._history_entries:
                html = self._build_history_html()
            else:
                html = self._build_empty_history_html()
            self.main_window.history_list.setHtml(html)
            cursor = self.main_window.history_list.textCursor()
            cursor.movePosition(cursor.Start)
            self.main_window.history_list.setTextCursor(cursor)

    def _build_history_html(self) -> str:
        """
        Construire le HTML de l'historique.

        Rendu compatible Qt QTextEdit (subset HTML/CSS limité) :
        - Barre colorée : colonne <td> de 3px avec bgcolor (border-left non supporté)
        - Badge ×N : <span> inline avec background-color
        - Entrée sur deux lignes : [heure] + badge type, puis le titre en dessous
        - Séparateurs temporels : ligne <hr> + texte centré
        """
        css = """
        body {
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 12px;
            margin: 2px 4px;
            padding: 0;
        }
        .ts      { color: #999999; }
        .title   { color: #222222; }
        .badge   { color: #666666; font-size: 11px; }
        .devices { color: #888888; font-size: 11px; }
        .detail  { color: #666666; font-size: 11px; }
        .sep     { color: #bbbbbb; font-size: 11px; }
        """

        html = f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head><body>\n'

        prev_ts = None
        prev_restauree = False
        for entry in self._history_entries:
            # Séparateur « Sessions précédentes » avant la 1re entrée restaurée :
            # il remplace le séparateur temporel à cet endroit.
            restauree = entry.get('restauree', False)
            if restauree and not prev_restauree:
                label = f"Sessions précédentes · {self._time_label(entry['timestamp'])}"
                html += (
                    f'<table width="100%" cellpadding="0" cellspacing="0">'
                    f'<tr><td><hr/></td>'
                    f'<td width="1" style="white-space:nowrap;" align="center">'
                    f'<span class="sep">&nbsp;{label}&nbsp;</span></td>'
                    f'<td><hr/></td></tr></table>\n'
                )
            # Séparateur temporel entre blocs distants
            elif prev_ts is not None:
                delta = prev_ts - entry['timestamp']
                if delta > timedelta(minutes=_TIME_GAP_MINUTES):
                    label = self._time_label(entry['timestamp'])
                    html += (
                        f'<table width="100%" cellpadding="0" cellspacing="0">'
                        f'<tr><td><hr/></td>'
                        f'<td width="1" style="white-space:nowrap;" align="center">'
                        f'<span class="sep">&nbsp;{label}&nbsp;</span></td>'
                        f'<td><hr/></td></tr></table>\n'
                    )
            prev_ts = entry['timestamp']
            prev_restauree = restauree

            style = _ACTION_STYLES.get(entry['action_type'], _ACTION_STYLES['system'])
            color = style['color']
            label = style['label']
            # Badge type : texte blanc sur fond coloré (plus fiable qu'emoji dans Qt).
            # Qt ignore le padding des <span> : la marge intérieure et l'alignement
            # passent par des espaces insécables (police à chasse fixe).
            label_padded = label.ljust(_BADGE_WIDTH).replace(' ', '&nbsp;')
            icon = (f'<span style="background-color:{color}; color:white; '
                    f'font-size:11px;">&nbsp;{label_padded}&nbsp;</span>')

            # Titre et badge
            safe_title = (entry['title']
                          .replace('&', '&amp;')
                          .replace('<', '&lt;')
                          .replace('>', '&gt;'))

            badge = ''
            if entry['count'] > 1:
                badge = (f'&nbsp;<span class="badge"'
                         f' style="background-color:#eeeeee; color:#555555;">'
                         f'&times;{entry["count"]} appareils</span>')

            # Durée de traitement (imports uniquement) — affichée en gris sur la ligne de titre
            duration_suffix = ''
            if entry.get('duration_ms') is not None:
                ms = entry['duration_ms']
                dur_str = f'{ms / 1000:.1f}s' if ms >= 1000 else f'{ms}ms'
                duration_suffix = (f'&nbsp;<span style="color:#999999; font-size:11px;">'
                                   f'{dur_str}</span>')


            # Ligne devices (sous-titre)
            devices_html = ''
            if entry['devices']:
                refs = ', '.join(entry['devices'][:8])
                if len(entry['devices']) > 8:
                    refs += f', \u2026 (+{len(entry["devices"]) - 8})'
                safe_refs = refs.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                devices_html = (
                    f'<tr><td bgcolor="{color}" width="3"></td>'
                    f'<td width="6"></td>'
                    f'<td><span class="devices">\u2514\u2500 {safe_refs}</span></td></tr>\n'
                )

            # Lignes de détail (==>)
            # Bloc d'alerte : une ligne « [!] » et les lignes « ==> » qui la suivent
            # directement (fourchettes de pages vides, conseil…). Surligné en jaune
            # avertissement — pas en rouge, réservé aux erreurs : rien n'a échoué,
            # il faut seulement vérifier.
            details_html = ''
            en_alerte = False
            for line in entry['details']:
                safe = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                debut = line.lstrip()
                # « - » : élément de liste sous le « ==> » précédent (marques
                # alignées), en retrait plus profond ; ne rompt pas un bloc d'alerte
                sous_element = debut.startswith('- ')
                if sous_element:
                    indent = '&nbsp;' * 10
                else:
                    indent = '&nbsp;&nbsp;' if debut.startswith('==>') else ''
                if debut.startswith('[!]'):
                    en_alerte = True
                elif not debut.startswith('==>') and not sous_element:
                    en_alerte = False
                if en_alerte:
                    gras = ' font-weight:bold;' if debut.startswith('[!]') else ''
                    cellule = (
                        f'<td bgcolor="{Config.Colors.WARNING_BG}">'
                        f'<span class="detail" style="color:{Config.Colors.WARNING_TEXT};{gras}">'
                        f'{indent}{safe}</span></td>'
                    )
                else:
                    cellule = f'<td><span class="detail">{indent}{safe}</span></td>'
                details_html += (
                    f'<tr><td bgcolor="{color}" width="3"></td>'
                    f'<td width="6"></td>'
                    f'{cellule}</tr>\n'
                )

            # Ligne d'action cliquable (ex. « Compléter le libellé »)
            if entry.get('lien'):
                href, texte = entry['lien']
                safe_href = href.replace('&', '&amp;').replace('"', '&quot;')
                safe_texte = texte.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                details_html += (
                    f'<tr><td bgcolor="{color}" width="3"></td>'
                    f'<td width="6"></td>'
                    f'<td><span class="detail">&nbsp;&nbsp;==&gt; </span>'
                    f'<a href="{safe_href}">{safe_texte}</a></td></tr>\n'
                )

            # Assemblage : table avec barre colorée en TD gauche
            html += (
                f'<table width="100%" cellpadding="0" cellspacing="1" style="margin:5px 0;">\n'
                f'<tr>'
                f'<td bgcolor="{color}" width="3"></td>'
                f'<td width="6"></td>'
                f'<td>'
                f'<span class="ts">[{entry["timestamp_str"]}]</span>&nbsp;'
                f'{icon}'
                f'</td></tr>\n'
                f'<tr><td bgcolor="{color}" width="3"></td>'
                f'<td width="6"></td>'
                f'<td>'
                f'<span class="title">{safe_title}</span>'
                f'{badge}'
                f'{duration_suffix}'
                f'</td></tr>\n'
                f'{devices_html}'
                f'{details_html}'
                f'</table>\n'
            )

        html += '</body></html>'
        return html

    @staticmethod
    def _time_label(ts: datetime) -> str:
        """Convertir un datetime en libellé relatif lisible."""
        delta = datetime.now() - ts
        minutes = int(delta.total_seconds() / 60)
        if minutes < 1:
            return "Il y a moins d'une minute"
        if minutes < 60:
            return f"Il y a {minutes} minute{'s' if minutes > 1 else ''}"
        maintenant = datetime.now()
        if ts.date() == maintenant.date():
            hours = minutes // 60
            return f"Il y a {hours} heure{'s' if hours > 1 else ''}"
        # Au-delà de la journée, « Il y a 52 heures » est illisible :
        # date explicite (entrées restaurées, ou application ouverte la veille).
        heure = ts.strftime('%H:%M')
        if ts.date() == (maintenant - timedelta(days=1)).date():
            return f"Hier à {heure}"
        mois = _MOIS_ABREGES[ts.month - 1]
        if ts.year != maintenant.year:
            return f"{ts.day} {mois} {ts.year} à {heure}"
        return f"{ts.day} {mois} à {heure}"

    # ── Statut et performance ──────────────────────────────────────────────────

    def show_status_message(self, message: str, timeout: int = None) -> None:
        """Afficher un message temporaire dans la barre de statut"""
        if timeout is None:
            timeout = Config.STATUS_MESSAGE_TIMEOUT
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(message, timeout)


    # ── Utilitaires ────────────────────────────────────────────────────────────

    def clear_history(self) -> None:
        """Vider l'historique des messages"""
        self._history_entries.clear()
        if hasattr(self.main_window, 'history_list'):
            self.main_window.history_list.setHtml(self._build_empty_history_html())

    @staticmethod
    def _build_empty_history_html() -> str:
        """État vide : message estompé et centré (au démarrage ou après effacement)."""
        return (
            f'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
            f'<p align="center" style="color:{Config.Colors.TEXT_MUTED}; '
            f'font-size:12px; margin-top:24px;">Aucune opération pour l\'instant</p>'
            f'</body></html>'
        )
