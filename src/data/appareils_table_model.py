"""
AppareillsTableModel — QAbstractTableModel pour la migration QTableWidget → QTableView.

Structure d'un record : (db_id, type, manufacturer, ref_modele,
                          commercial_ref, other_ref, category, notes, pieces_count)

Usage :
    model = AppareillsTableModel()
    model.load_records(records)
    view.setModel(model)
"""

from typing import Optional, Tuple

import qtawesome as qta
from PyQt5.QtCore import Qt, QAbstractTableModel, QEvent, QModelIndex, QRect, QRectF, QSize, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate

from src.core.config import Config, pluralize

# Colonnes Type (0) et Fabricant (1) — cibles des suggestions par similarité.
_SUGGESTION_COLS = (0, 1)
_SUGGESTION_BG = QColor('#FFF8E1')   # jaune pâle, distinct de l'alerte doublons
# Champ de chaque colonne Type/Fabricant, pour les auto-complétions à vérifier
_CHAMP_PAR_COLONNE = {0: 'type', 1: 'manufacturer'}
# Auto-complétions à vérifier : fond lavande, distinct du jaune des suggestions
# et assez soutenu pour ne pas se confondre avec la teinte d'une ligne sur deux.
_AUTOCOMPLETE_BG = QColor('#DDE2F7')


class AppareillsTableModel(QAbstractTableModel):
    """Modèle de données tabulaires pour les appareils.

    Remplace QTableWidget côté données. La vue (QTableView ou QTableWidget)
    est décorrelée du stockage.

    Signaux :
        cell_edited(row, col, old_value, new_value) — émis par setData(),
        remplace le signal itemChanged de QTableWidget.

    Virtual scrolling (USE_VIRTUAL_SCROLL) :
        _display_count : nombre de lignes actuellement exposées à la vue.
        rowCount() retourne _display_count (pas len(_records)).
        canFetchMore() / fetchMore() révèlent FETCH_CHUNK lignes supplémentaires
        quand l'utilisateur approche du bas de liste — sans requête DB.
    """

    # Signal custom — remplace itemChanged de QTableWidget
    cell_edited = pyqtSignal(int, int, str, str)  # row, col, old_value, new_value

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self._records = []            # List[Tuple]: (db_id, col1..colN, pieces_count)
        self._display_count = 0       # Lignes actuellement visibles (virtual scroll)
        self._headers = Config.UI_HEADERS
        self._main_window = main_window
        self._search_term = None
        # Suggestions Type/Marque par similarité en attente de validation.
        # {db_id: [candidat_dict, ...]} — alimenté par set_pending_suggestions().
        # Le rendu (teinte de fond + texte fantôme + icône) est assuré par
        # SuggestionCellDelegate ; le modèle n'expose que l'état et le BackgroundRole.
        self._pending_suggestions = {}
        # Champs auto-complétés à l'import et non vérifiés (v3.89.0), rendus en
        # italique : {db_id: {champ: (source, accord, total)}}. Indexé par db_id,
        # donc indépendant de la page chargée — alimenté par set_autocompletes().
        self._autocompletes = {}

    # ── API Qt obligatoire ───────────────────────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return self._display_count

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._headers)

    def canFetchMore(self, parent=QModelIndex()) -> bool:
        if parent.isValid():
            return False
        if not Config.USE_VIRTUAL_SCROLL:
            return False
        return self._display_count < len(self._records)

    def fetchMore(self, parent=QModelIndex()):
        """Révèle FETCH_CHUNK lignes supplémentaires depuis _records (déjà en mémoire)."""
        if parent.isValid():
            return
        remaining = len(self._records) - self._display_count
        to_fetch = min(Config.FETCH_CHUNK, remaining)
        if to_fetch <= 0:
            return
        self.beginInsertRows(QModelIndex(), self._display_count, self._display_count + to_fetch - 1)
        self._display_count += to_fetch
        self.endInsertRows()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= self._display_count:
            return None
        row, col = index.row(), index.column()
        record = self._records[row]

        if role in (Qt.DisplayRole, Qt.EditRole):
            if col < len(Config.DB_HEADERS):
                # record[0] = db_id, donc les données commencent à record[1]
                return str(record[col + 1] or "")
            else:
                # Dernière colonne : Nb Pièces (record[-1] = pieces_count)
                return str(record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0)

        elif role == Qt.UserRole:
            # db_id — remplace item.data(Qt.UserRole) dans l'ensemble du code
            return record[0]

        elif role == Qt.BackgroundRole:
            if col == len(Config.DB_HEADERS):   # Nb Pièces
                pieces = record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0
                color = QColor(220, 248, 198) if pieces > 0 else QColor(248, 248, 248)
                return QBrush(color)
            # Suggestion Type/Marque en attente : teinte douce sur les cellules concernées.
            if col in _SUGGESTION_COLS and self._pending_suggestions.get(record[0]):
                return QBrush(_SUGGESTION_BG)
            # Auto-complétion à vérifier : teinte lavande sur la cellule concernée.
            if self.autocompletion_de(record[0], col):
                return QBrush(_AUTOCOMPLETE_BG)
            # Highlight de recherche : délégué au service (Phase 3+)
            return None

        elif role == Qt.FontRole:
            if self.autocompletion_de(record[0], col):
                police = QFont()
                police.setItalic(True)
                return police

        elif role == Qt.ToolTipRole:
            if col == len(Config.DB_HEADERS):
                pieces = record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0
                return pluralize(pieces, 'pièce associée', 'pièces associées') if pieces > 0 else "Aucune pièce associée"
            if col in _SUGGESTION_COLS:
                suggestions = self._pending_suggestions.get(record[0])
                if suggestions:
                    from ..services.reference_similarity_service import infobulle_candidat
                    return infobulle_candidat(suggestions[0])
                prov = self.autocompletion_de(record[0], col)
                if prov:
                    source, accord, total = prov
                    confiance = f"{accord}/{total}" if accord is not None else "confiance inconnue"
                    return (f"Auto-complété d'après {source or '?'} ({confiance}) — à vérifier : "
                            f"cliquez sur la coche (ou clic droit « Marquer comme vérifié »), "
                            f"ou corrigez la valeur")

        return None

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.EditRole:
            return False
        row, col = index.row(), index.column()
        if row >= self._display_count:
            return False
        old_value = self.data(index, Qt.DisplayRole) or ""
        new_value = str(value)
        record = list(self._records[row])
        if col < len(Config.DB_HEADERS):
            record[col + 1] = new_value
        self._records[row] = tuple(record)
        self._oublier_autocompletion(record[0], col, old_value, new_value)
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole, Qt.FontRole])
        self.cell_edited.emit(row, col, old_value, new_value)
        return True

    def set_field_value(self, row: int, col: int, value) -> bool:
        """Écrit une valeur sur une ligne CHARGÉE (présente dans _records), même hors
        page virtuelle (row >= _display_count), SANS passer par un QModelIndex (que la
        vue refuserait pour une ligne non affichée).

        Réservé aux écritures programmatiques sur des lignes potentiellement non
        affichées — typiquement l'application d'une suggestion Type/Marque validée sur
        un appareil au-delà de la page virtuelle initiale. Émet TOUJOURS cell_edited
        (sauvegarde / undo / historique en aval) ; n'émet dataChanged que si la ligne
        est affichée (la vue ignore — et Qt invalide — un index hors rowCount()).

        Contrairement à setData(), n'altère ni index() ni le contrat Qt du modèle :
        aucun impact sur la sélection, le tri, la suppression ou les délégués.

        Returns:
            bool: True si la ligne est chargée et l'écriture effectuée.
        """
        if not (0 <= row < len(self._records)) or col >= len(Config.DB_HEADERS):
            return False
        old_value = self.value_at(row, col)
        new_value = str(value)
        record = list(self._records[row])
        record[col + 1] = new_value
        self._records[row] = tuple(record)
        self._oublier_autocompletion(record[0], col, old_value, new_value)
        if row < self._display_count:
            idx = self.index(row, col)
            self.dataChanged.emit(idx, idx, [Qt.DisplayRole, Qt.EditRole, Qt.FontRole])
        self.cell_edited.emit(row, col, old_value, new_value)
        return True

    def value_at(self, row: int, col: int) -> str:
        """Valeur texte d'une cellule lue directement depuis _records, sans le garde
        d'affichage de data() (utilisable sur les lignes chargées hors page virtuelle).

        Renvoie '' si la ligne est hors limites. Réplique le mapping de data() :
        record[0] = db_id, données à partir de record[col+1] ; dernière colonne =
        pieces_count (record[-1])."""
        if not (0 <= row < len(self._records)):
            return ""
        record = self._records[row]
        if col < len(Config.DB_HEADERS):
            return str(record[col + 1] or "")
        return str(record[-1] if len(record) > len(Config.DB_HEADERS) + 1 else 0)

    def flags(self, index) -> Qt.ItemFlags:
        if not index.isValid() or index.row() >= self._display_count:
            return Qt.NoItemFlags
        if index.column() == len(Config.DB_HEADERS):    # Nb Pièces — lecture seule
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        # Colonne figée « Nb pièces » : libellé court à l'écran (« Nb pièces » était
        # tronqué en « pièc » dans ses 60 px), nom complet en infobulle.
        # Config.UI_HEADERS n'est pas modifié : il sert aussi ailleurs.
        is_pieces_col = orientation == Qt.Horizontal and section == len(Config.DB_HEADERS)
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                if is_pieces_col:
                    return "Pièces"
                return self._headers[section] if section < len(self._headers) else None
            else:
                return str(section + 1)   # 1-indexé comme l'ancien setVerticalHeaderItem
        if role == Qt.ToolTipRole and is_pieces_col:
            return "Nombre de pièces associées"
        # Repère « à vérifier » du numéro de ligne : dessiné par l'en-tête de
        # CustomTableView (la feuille de style écraserait ForegroundRole/FontRole).
        if (role == Qt.ToolTipRole and orientation == Qt.Vertical
                and self.ligne_a_verifier(section)):
            return "Ligne auto-complétée à vérifier"
        return None

    def ligne_a_verifier(self, row) -> bool:
        """True si la ligne affichée porte au moins une auto-complétion non vérifiée."""
        if not (0 <= row < self._display_count):
            return False
        return bool(self._autocompletes.get(self._records[row][0]))

    # ── API custom ───────────────────────────────────────────────────────────

    def load_records(self, records: list):
        """Charge un lot d'enregistrements et réinitialise le modèle.

        Avec USE_VIRTUAL_SCROLL, expose seulement FETCH_INITIAL lignes
        initialement ; fetchMore() révèle la suite au fur et à mesure.
        Sans virtual scroll, toutes les lignes sont exposées immédiatement.
        """
        self.beginResetModel()
        self._records = list(records)
        if Config.USE_VIRTUAL_SCROLL:
            self._display_count = min(Config.FETCH_INITIAL, len(self._records))
        else:
            self._display_count = len(self._records)
        self.endResetModel()

    def get_db_id(self, row: int):
        """Retourne le db_id de la ligne, ou None si hors limites.

        Remplace item(row, col).data(Qt.UserRole) dans les 20+ endroits du code.
        """
        return self._records[row][0] if 0 <= row < len(self._records) else None

    def loaded_record_count(self) -> int:
        """Nombre de lignes chargées en mémoire pour la page courante (peut être
        supérieur à rowCount()/_display_count tant que le virtual scroll n'a pas
        tout révélé — utilisé pour la navigation cellule vide, qui doit pouvoir
        atteindre une ligne pas encore affichée)."""
        return len(self._records)

    def find_incomplete_row(self, start_row: int, direction: str) -> Optional[Tuple[int, int]]:
        """Cherche, dans les lignes déjà chargées de la page courante (pas
        seulement celles révélées par le virtual scroll), la prochaine ligne
        incomplète depuis start_row : Type OU Fabricant vide — même définition
        que le compteur « Lignes à traiter » (_get_incomplete_condition).

        Retourne (ligne, colonne à remplir) — Type (0) s'il est vide, sinon
        Fabricant (1) — ou None si rien trouvé sur cette page : l'appelant doit
        alors passer à la page précédente/suivante pour poursuivre la recherche,
        ce qui permet à la navigation de respecter le tri/filtres/recherche
        courants au lieu d'imposer une vue indépendante."""
        step = 1 if direction == 'down' else -1
        r = start_row + step
        while 0 <= r < len(self._records):
            for col in (0, 1):
                val = self._records[r][col + 1]
                if not val or not str(val).strip():
                    return r, col
            r += step
        return None

    def find_a_verifier_row(self, start_row: int, direction: str) -> Optional[Tuple[int, int]]:
        """Pendant de find_incomplete_row pour les lignes auto-complétées à
        vérifier (même source que le numéro de ligne orange, ligne_a_verifier) :
        prochaine ligne chargée de la page depuis start_row, avec la colonne à
        contrôler — Type (0) s'il est auto-complété, sinon Fabricant (1) — ou
        None si rien sur cette page."""
        step = 1 if direction == 'down' else -1
        r = start_row + step
        while 0 <= r < len(self._records):
            champs = self._autocompletes.get(self._records[r][0])
            if champs:
                for col in (0, 1):
                    if _CHAMP_PAR_COLONNE[col] in champs:
                        return r, col
            r += step
        return None

    def a_des_autocompletes(self) -> bool:
        """Au moins un appareil auto-complété à vérifier, toutes pages confondues."""
        return bool(self._autocompletes)

    def reveal_row(self, row: int):
        """Force la révélation (virtual scroll) jusqu'à la ligne row incluse,
        pour qu'elle devienne sélectionnable/visible dans la vue."""
        while row >= self._display_count and self.canFetchMore():
            self.fetchMore()

    def update_pieces_count(self, row: int, count: int):
        """Met à jour pieces_count (record[-1]) sans émettre cell_edited.

        Utilisé exclusivement par PiecesCountService après association/suppression
        de pièce. N'est pas une édition utilisateur → pas de sauvegarde déclenchée.
        Si la ligne n'est pas encore visible (virtual scroll), met à jour _records
        silencieusement — elle affichera la bonne valeur quand elle deviendra visible.
        """
        if not (0 <= row < len(self._records)):
            return
        record = list(self._records[row])
        record[-1] = count
        self._records[row] = tuple(record)
        # Émettre dataChanged uniquement si la ligne est visible
        if row < self._display_count:
            idx = self.index(row, len(self._headers) - 1)
            self.dataChanged.emit(idx, idx, [Qt.DisplayRole, Qt.BackgroundRole, Qt.ToolTipRole])

    def find_row_by_db_id(self, db_id: int):
        """Retourne l'index de ligne pour un db_id donné, ou None si absent."""
        for i, rec in enumerate(self._records):
            if rec[0] == db_id:
                return i
        return None

    # ── Suggestions Type/Marque par similarité ──────────────────────────────
    def set_pending_suggestions(self, suggestions_by_db_id):
        """Remplace la map des suggestions en attente et rafraîchit les cellules
        Type/Marque concernées (anciennes ET nouvelles lignes affectées).

        suggestions_by_db_id : {db_id: [candidat_dict, ...]}.
        """
        affected = set(self._pending_suggestions.keys()) | set(suggestions_by_db_id.keys())
        self._pending_suggestions = dict(suggestions_by_db_id)
        self._emit_data_changed_for_db_ids(affected)

    def add_pending_suggestions(self, suggestions_by_db_id):
        """Fusionne des suggestions dans la map existante (sans tout remplacer).

        Utilisé par le déclenchement manuel (menu contextuel) pour ne pas effacer
        les suggestions issues d'un import précédent.
        """
        self._pending_suggestions.update(suggestions_by_db_id)
        self._emit_data_changed_for_db_ids(set(suggestions_by_db_id.keys()))

    def clear_suggestion(self, db_id):
        """Dissipe l'indicateur pour une ligne (acceptée / ignorée / éditée)."""
        if db_id in self._pending_suggestions:
            del self._pending_suggestions[db_id]
            self._emit_data_changed_for_db_ids({db_id})

    def get_suggestions_for_db_id(self, db_id):
        """Retourne la liste des candidats pour un db_id, ou [] si aucune."""
        return self._pending_suggestions.get(db_id, [])

    # ── Auto-complétions à vérifier (v3.89.0) ───────────────────────────────
    def set_autocompletes(self, par_appareil):
        """Remplace la map des champs auto-complétés non vérifiés et rafraîchit
        les cellules concernées (anciennes ET nouvelles lignes).

        par_appareil : {db_id: {champ: (source, accord, total)}}.
        """
        affected = set(self._autocompletes) | set(par_appareil)
        self._autocompletes = {k: dict(v) for k, v in par_appareil.items()}
        self._emit_data_changed_for_db_ids(affected)
        self._emit_header_changed_for_db_ids(affected)

    def autocompletion_de(self, db_id, col):
        """(source, accord, total) si la cellule porte une auto-complétion non
        vérifiée, sinon None."""
        champ = _CHAMP_PAR_COLONNE.get(col)
        if champ is None:
            return None
        return self._autocompletes.get(db_id, {}).get(champ)

    def ids_autocompletes(self, db_ids):
        """Ceux des db_ids fournis qui portent au moins une auto-complétion."""
        return [i for i in db_ids if self._autocompletes.get(i)]

    def _oublier_autocompletion(self, db_id, col, ancienne, nouvelle):
        """Une valeur modifiée n'est plus « auto-complétée » : même règle que le
        déclencheur SQL (la casse seule ne compte pas), appliquée sans attendre le
        prochain rafraîchissement depuis la base."""
        champ = _CHAMP_PAR_COLONNE.get(col)
        champs = self._autocompletes.get(db_id)
        if not champs or champ not in champs:
            return
        if (ancienne or '').lower() != (nouvelle or '').lower():
            del champs[champ]
            if not champs:
                del self._autocompletes[db_id]
                self._emit_header_changed_for_db_ids([db_id])

    def incomplete_records(self):
        """Retourne [(db_id, ref_modele, commercial_ref)] pour toutes les lignes
        CHARGÉES (pas seulement visibles) dont Type OU Marque est vide.

        Record : (db_id, type, manufacturer, ref_modele, commercial_ref, ...).
        Utilisé par le scan global de suggestions (menu Données)."""
        out = []
        for rec in self._records:
            type_v = (rec[1] or '').strip() if len(rec) > 1 else ''
            mfr_v = (rec[2] or '').strip() if len(rec) > 2 else ''
            if type_v and mfr_v:
                continue
            ref_modele = (rec[3] or '').strip() if len(rec) > 3 else ''
            commercial_ref = (rec[4] or '').strip() if len(rec) > 4 else ''
            out.append((rec[0], ref_modele, commercial_ref))
        return out

    def safe_suggestions(self):
        """Suggestions applicables en masse **sans concurrence** : exactement UN
        candidat trouvé (aucune marque alternative). Retourne [(db_id, candidat)].

        Le critère est l'absence d'ambiguïté (1 seul candidat), pas le palier :
        une suggestion à plusieurs candidats — seul cas réellement risqué pour la
        confusion inter-marques — est exclue et exige un choix humain."""
        return [(db_id, cands[0]) for db_id, cands in self._pending_suggestions.items()
                if len(cands) == 1]

    def suggestions_snapshot(self, lire_hors_page=None):
        """Décrit chaque appareil ayant des suggestions en attente, pour alimenter la
        fenêtre de validation. Chaque entrée :
        {db_id, ref_modele, commercial_ref, current_type, current_manufacturer,
         candidates: [candidat_dict, ...], hors_page: bool}.

        Record : (db_id, type, manufacturer, ref_modele, commercial_ref, ...).

        Après un import, le tableau est rechargé sans filtre (page 1, tri id DESC) :
        les appareils existants touchés par l'import ont d'anciens id et ne sont
        pas chargés, alors que la bannière les compte.

        lire_hors_page : callable([db_id]) -> {db_id: (type, manufacturer,
            ref_modele, commercial_ref)} ou None si la lecture a échoué. Fourni par
            l'appelant (le modèle n'accède pas à la base). Les db_id qu'il ne
            renvoie pas n'existent plus : leurs suggestions sont retirées, pour que
            bannière et fenêtre restent d'accord. Un échec de lecture (None) ne
            retire rien. Sans ce callable, les db_id hors page sont ignorés."""
        by_id = {rec[0]: rec for rec in self._records}
        manquants = [db_id for db_id in self._pending_suggestions if db_id not in by_id]
        hors_page = {}
        if manquants and lire_hors_page is not None:
            lus = lire_hors_page(manquants)
            if lus is not None:
                hors_page = lus
                disparus = [db_id for db_id in manquants if db_id not in lus]
                for db_id in disparus:
                    del self._pending_suggestions[db_id]
        out = []
        for db_id, cands in self._pending_suggestions.items():
            rec = by_id.get(db_id)
            if rec is not None:
                type_v, mfr_v, ref_modele, commercial_ref = (
                    rec[1] if len(rec) > 1 else '', rec[2] if len(rec) > 2 else '',
                    rec[3] if len(rec) > 3 else '', rec[4] if len(rec) > 4 else '')
            elif db_id in hors_page:
                type_v, mfr_v, ref_modele, commercial_ref = hors_page[db_id]
            else:
                continue
            out.append({
                'db_id': db_id,
                'ref_modele': ref_modele or '',
                'commercial_ref': commercial_ref or '',
                'current_type': type_v or '',
                'current_manufacturer': mfr_v or '',
                'candidates': list(cands),
                'hors_page': rec is None,
            })
        return out

    @property
    def pending_suggestions_count(self):
        """Nombre d'appareils ayant une suggestion en attente (API publique)."""
        return len(self._pending_suggestions)

    def _emit_data_changed_for_db_ids(self, db_ids):
        """Émet dataChanged sur les colonnes Type/Marque des lignes visibles
        correspondant aux db_id fournis."""
        for db_id in db_ids:
            row = self.find_row_by_db_id(db_id)
            if row is not None and row < self._display_count:
                self.dataChanged.emit(
                    self.index(row, _SUGGESTION_COLS[0]),
                    self.index(row, _SUGGESTION_COLS[-1]),
                    [Qt.BackgroundRole, Qt.DecorationRole, Qt.ToolTipRole, Qt.FontRole],
                )

    def _emit_header_changed_for_db_ids(self, db_ids):
        """Rafraîchit le numéro de ligne (repère « à vérifier ») des lignes
        affichées correspondant aux db_id fournis."""
        for db_id in db_ids:
            row = self.find_row_by_db_id(db_id)
            if row is not None and row < self._display_count:
                self.headerDataChanged.emit(Qt.Vertical, row, row)

    def set_search_term(self, term):
        """Met à jour le terme de recherche pour le highlight (Phase 3+).

        Appelé depuis load_data() après chargement. Déclenche un refresh
        des BackgroundRole sur toutes les cellules.
        """
        self._search_term = term
        if self._display_count > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self._display_count - 1, len(self._headers) - 1),
                [Qt.BackgroundRole]
            )


class PiecesCountDelegate(QStyledItemDelegate):
    """Peint un badge pill coloré dans la colonne Nb Pièces.

    - count > 0 → vert #27ae60
    - count == 0 → orange #e67e22
    Gère la sélection : fond highlight Qt quand la cellule est sélectionnée.
    """

    _COLOR_HAS_PIECES = QColor("#27ae60")
    _COLOR_NO_PIECES  = QColor("#e67e22")
    _COLOR_BG         = QColor(248, 248, 248)

    def paint(self, painter, option, index):
        painter.save()

        # Fond : couleur sélection ou gris très clair (même que BackgroundRole)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, self._COLOR_BG)

        # Valeur
        try:
            count = int(index.data(Qt.DisplayRole) or 0)
        except (ValueError, TypeError):
            count = 0

        badge_color = self._COLOR_HAS_PIECES if count > 0 else self._COLOR_NO_PIECES

        # Geometry du badge pill (centré dans la cellule)
        badge_w, badge_h = 34, 18
        cx = option.rect.center().x()
        cy = option.rect.center().y()
        badge_rect = QRectF(cx - badge_w / 2, cy - badge_h / 2, badge_w, badge_h)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(badge_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(badge_rect, 9, 9)

        # Texte blanc centré
        if option.state & QStyle.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(QColor("white"))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(badge_rect.toRect(), Qt.AlignCenter, str(count))

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(50, 26)


class SuggestionCellDelegate(QStyledItemDelegate):
    """Delegate des colonnes Type/Marque : affiche la suggestion en attente
    directement dans la case (texte fantôme grisé) + une icône cliquable à droite.

    - Clic sur l'icône → `accept_handler(index, suggestions)` (défini par
      l'appelant) : applique le candidat unique, ou ouvre le chooser si plusieurs.
    - Clic ailleurs dans la case → comportement normal (sélection/édition).

    Le delegate ne décide PAS de l'application : il délègue à `accept_handler`,
    qui passe par le pipeline model.setData (jamais d'accès DB direct).
    """

    _ICON_SIZE = 16
    _GHOST_COLOR = QColor('#9e9e9e')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.accept_handler = None      # callable(index, suggestions) -> None
        self.verify_handler = None      # callable(index) -> None (coche « vérifié »)
        self._icon = None               # qta.icon, créé paresseusement
        self._icon_verifier = None

    def _get_icon(self):
        if self._icon is None:
            self._icon = qta.icon('fa5s.magic', color='#f39c12')
        return self._icon

    def _get_icon_verifier(self):
        if self._icon_verifier is None:
            self._icon_verifier = qta.icon('fa5s.check-circle', color='#5c6bc0')
        return self._icon_verifier

    @staticmethod
    def _a_verifier(index):
        """True si la cellule porte une auto-complétion non vérifiée."""
        model = index.model()
        if not (hasattr(model, 'autocompletion_de') and hasattr(model, 'get_db_id')):
            return False
        db_id = model.get_db_id(index.row())
        return db_id is not None and bool(model.autocompletion_de(db_id, index.column()))

    def _icon_rect(self, rect):
        s = self._ICON_SIZE
        y = rect.top() + (rect.height() - s) // 2
        x = rect.right() - s - 4
        return QRect(int(x), int(y), s, s)

    @staticmethod
    def _top_candidate(index):
        model = index.model()
        if not (hasattr(model, 'get_suggestions_for_db_id') and hasattr(model, 'get_db_id')):
            return None
        db_id = model.get_db_id(index.row())
        if db_id is None:
            return None
        suggestions = model.get_suggestions_for_db_id(db_id)
        return suggestions[0] if suggestions else None

    def paint(self, painter, option, index):
        # Fond (BackgroundRole), sélection et texte réel (vide ici) : rendu standard.
        super().paint(painter, option, index)

        cand = self._top_candidate(index)
        if cand is None:
            # Pas de suggestion : coche « Marquer comme vérifié » si auto-complétée.
            if self._a_verifier(index):
                painter.save()
                self._get_icon_verifier().paint(painter, self._icon_rect(option.rect))
                painter.restore()
            return

        painter.save()
        # Icône d'action à droite
        self._get_icon().paint(painter, self._icon_rect(option.rect))

        # Texte fantôme (valeur suggérée) uniquement si la case est réellement vide
        if not (index.data(Qt.DisplayRole) or ''):
            ghost = cand.get('type', '') if index.column() == 0 else cand.get('manufacturer', '')
            if ghost:
                painter.setPen(self._GHOST_COLOR)
                f = painter.font()
                f.setItalic(True)
                painter.setFont(f)
                text_rect = option.rect.adjusted(6, 0, -(self._ICON_SIZE + 8), 0)
                elided = painter.fontMetrics().elidedText(ghost, Qt.ElideRight, text_rect.width())
                painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if (event.type() == QEvent.MouseButtonRelease
                and event.button() == Qt.LeftButton
                and self._top_candidate(index) is not None
                and self._icon_rect(option.rect).contains(event.pos())):
            if callable(self.accept_handler):
                db_id = model.get_db_id(index.row())
                suggestions = model.get_suggestions_for_db_id(db_id)
                self.accept_handler(index, suggestions)
            return True
        if (event.type() == QEvent.MouseButtonRelease
                and event.button() == Qt.LeftButton
                and self._top_candidate(index) is None
                and self._a_verifier(index)
                and self._icon_rect(option.rect).contains(event.pos())):
            if callable(self.verify_handler):
                self.verify_handler(index)
            return True
        return super().editorEvent(event, model, option, index)
