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

import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from .qt_imports import QMessageBox, QTimer

from src.core.config import Config
from src.core.logger import app_logger


# ── Styles par type d'action ───────────────────────────────────────────────────
# label : badge texte court affiché à la place d'une icône emoji (emojis non fiables dans Qt)
_ACTION_STYLES: Dict[str, Dict[str, str]] = {
    'edit':   {'color': '#4A9EFF', 'label': 'MOD'},
    'import': {'color': '#34D058', 'label': 'IMP'},
    'export': {'color': '#9B59B6', 'label': 'EXP'},
    'delete': {'color': '#E05252', 'label': 'SUP'},
    'undo':   {'color': '#F39C12', 'label': 'ANN'},
    'piece':  {'color': '#1ABC9C', 'label': 'PIC'},
    'system': {'color': '#95A5A6', 'label': 'SYS'},
}

_MAX_HISTORY = 100          # Nombre max d'entrées visibles
_TIME_GAP_MINUTES = 5       # Seuil pour insérer un séparateur temporel

# Regex pour parser une ligne "==> Field : 'old' → 'new'"
_RE_ARROW = re.compile(r"==>\s*(.+?)\s*:\s*'(.*)'\s*→\s*'(.*)'")

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
    if any(k in m for k in ('suppression', 'supprimé', 'supprimée', '❌', 'erreur', 'error', 'échec')):
        return 'delete'
    if any(k in m for k in ('export csv', 'html marques', 'html détails', 'export html', 'export {')):
        return 'export'
    if 'export' in m and any(k in m for k in ('lignes', 'résultats', 'marques', 'format')):
        return 'export'
    if '📊 import' in m or 'lignes extraites' in m or 'appareils créés' in m or 'appareils :' in m:
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


class UserInteractionService:
    """
    Service spécialisé pour les interactions avec l'utilisateur.

    Historique v2 : modèle structuré, agrégation cross-appareils,
    code couleur par type d'action, barres verticales CSS, séparateurs temporels.
    """

    def __init__(self, main_window):
        self.main_window = main_window
        self._history_entries: List[Dict[str, Any]] = []

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
            if (hasattr(self.main_window, 'total_rows') and
                    self.main_window.use_pagination and
                    self.main_window.total_rows > Config.MAX_DISPLAY_ROWS):
                self.main_window.table_controller.size_label.setText(
                    f"Affichées : {displayed_count} / Total : {self.main_window.total_rows:,}")
            else:
                self.main_window.table_controller.size_label.setText(f"Lignes : {displayed_count:,}")
        elif hasattr(self.main_window, 'counter_label'):
            if (hasattr(self.main_window, 'total_rows') and
                    self.main_window.use_pagination and
                    self.main_window.total_rows > Config.MAX_DISPLAY_ROWS):
                self.main_window.counter_label.setText(
                    f"Affichées : {displayed_count} / Total : {self.main_window.total_rows:,}")
            else:
                self.main_window.counter_label.setText(f"Lignes : {displayed_count:,}")

    # ── Historique ─────────────────────────────────────────────────────────────

    def add_to_history(self, message: str, duration_ms: Optional[int] = None) -> None:
        """
        Ajouter un message à l'historique.
        API identique à v1 — les appelants n'ont pas à changer.

        Args:
            message: Texte brut de l'action (timestamp ajouté automatiquement)
            duration_ms: Durée optionnelle en millisecondes (affichée en gris pour les imports)

        Logique d'agrégation :
        - Si le nouveau message est un edit mono-champ avec le même (field, new_value)
          que la dernière entrée → incrémenter count et ajouter le device.
        - Sinon → insérer une nouvelle entrée en tête.
        """
        now = datetime.now()
        entry = _parse_entry(message, now)
        if duration_ms is not None:
            entry['duration_ms'] = duration_ms

        # Tentative d'agrégation avec la dernière entrée
        if (entry['agg_key'] is not None and
                self._history_entries and
                self._history_entries[0]['agg_key'] == entry['agg_key']):
            last = self._history_entries[0]
            last['count'] += 1
            if entry['devices']:
                last['devices'].extend(entry['devices'])
            # Mettre à jour le timestamp pour refléter la dernière modification
            last['timestamp'] = now
            last['timestamp_str'] = now.strftime('%H:%M:%S')
        else:
            self._history_entries.insert(0, entry)
            if len(self._history_entries) > _MAX_HISTORY:
                self._history_entries = self._history_entries[:_MAX_HISTORY]

        self._refresh_display()

    def _refresh_display(self) -> None:
        """Reconstruire et afficher le HTML de l'historique."""
        if hasattr(self.main_window, 'history_list'):
            html = self._build_history_html()
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
        .sep     { color: #bbbbbb; font-size: 10px; }
        """

        html = f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head><body>\n'

        prev_ts = None
        for entry in self._history_entries:
            # Séparateur temporel entre blocs distants
            if prev_ts is not None:
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

            style = _ACTION_STYLES.get(entry['action_type'], _ACTION_STYLES['system'])
            color = style['color']
            label = style['label']
            # Badge type : texte blanc sur fond coloré (plus fiable qu'emoji dans Qt)
            icon = (f'<span style="background-color:{color}; color:white; '
                    f'font-size:10px; padding:1px 4px;">{label}</span>')

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
                duration_suffix = (f'&nbsp;<span style="color:#999999; font-size:10px;">'
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
            details_html = ''
            for line in entry['details']:
                safe = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                indent = '&nbsp;&nbsp;' if line.lstrip().startswith('==>') else ''
                details_html += (
                    f'<tr><td bgcolor="{color}" width="3"></td>'
                    f'<td width="6"></td>'
                    f'<td><span class="detail">{indent}{safe}</span></td></tr>\n'
                )

            # Assemblage : table avec barre colorée en TD gauche
            html += (
                f'<table width="100%" cellpadding="0" cellspacing="1" style="margin:2px 0;">\n'
                f'<tr>'
                f'<td bgcolor="{color}" width="3"></td>'
                f'<td width="6"></td>'
                f'<td>'
                f'<span class="ts">[{entry["timestamp_str"]}]</span>&nbsp;'
                f'{icon}&nbsp;'
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
        hours = minutes // 60
        return f"Il y a {hours} heure{'s' if hours > 1 else ''}"

    # ── Statut et performance ──────────────────────────────────────────────────

    def show_status_message(self, message: str, timeout: int = None) -> None:
        """Afficher un message temporaire dans la barre de statut"""
        if timeout is None:
            timeout = Config.STATUS_MESSAGE_TIMEOUT
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(message, timeout)

    def show_performance_indicator(self, message: str, duration_ms: Optional[int] = None) -> None:
        """Afficher un indicateur de performance"""
        if hasattr(self.main_window, 'perf_label'):
            perf_message = f"⚡ {message} ({duration_ms}ms)" if duration_ms else f"⚡ {message}"
            self.main_window.perf_label.setText(perf_message)
            if duration_ms is not None:
                QTimer.singleShot(3000, lambda: self._reset_performance_indicator())

    def _reset_performance_indicator(self) -> None:
        """Remettre l'indicateur de performance à "Prêt" """
        if hasattr(self.main_window, 'perf_label'):
            self.main_window.perf_label.setText("⚡ Prêt")

    # ── Utilitaires ────────────────────────────────────────────────────────────

    def clear_history(self) -> None:
        """Vider l'historique des messages"""
        self._history_entries.clear()
        if hasattr(self.main_window, 'history_list'):
            empty_html = (
                f'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
                f'<p style="color:{Config.Colors.TEXT_MUTED}; font-family: monospace; '
                f'font-size:12px; margin:4px;">Historique vide</p>'
                f'</body></html>'
            )
            self.main_window.history_list.setHtml(empty_html)

    def get_history_count(self) -> int:
        """Obtenir le nombre d'entrées dans l'historique"""
        return len(self._history_entries)
