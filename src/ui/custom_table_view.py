"""
CustomTableView — QTableView de remplacement pour CustomTableWidget.

Réplique le comportement clavier de CustomTableWidget(QTableWidget) et expose
des méthodes de compatibilité QTableWidget pour que les services non encore
migrés (Phase 4) continuent à fonctionner sans modification.

Phase 2 de la migration QTableWidget → QTableView.
Production : non activé tant que Config.USE_TABLE_VIEW = False.
"""

from PyQt5.QtWidgets import QTableView, QApplication, QTableWidgetItem, QAbstractItemView, QHeaderView, QMenu
from PyQt5.QtCore import Qt, QTimer, QItemSelection, QItemSelectionModel
from PyQt5.QtGui import QKeyEvent, QPainter, QColor, QFont


class _SelectionRangeCompat:
    """Simule QTableWidgetSelectionRange pour les services non encore migrés.

    Permet à tout code qui appelle .selectedRanges()[0].topRow() etc. de
    continuer à fonctionner sans modification jusqu'à la Phase 4.
    """

    def __init__(self, top: int, left: int, bottom: int, right: int):
        self._top = top
        self._left = left
        self._bottom = bottom
        self._right = right

    def topRow(self) -> int:
        return self._top

    def bottomRow(self) -> int:
        return self._bottom

    def leftColumn(self) -> int:
        return self._left

    def rightColumn(self) -> int:
        return self._right

    def rowCount(self) -> int:
        return self._bottom - self._top + 1

    def columnCount(self) -> int:
        return self._right - self._left + 1


class CustomTableView(QTableView):
    """QTableView avec gestion clavier identique à CustomTableWidget.

    Deux catégories de méthodes :
    1. Comportement clavier — réplique exacte de CustomTableWidget.
    2. Compatibilité QTableWidget — permet aux services Phase 3 non encore
       migrés de continuer à fonctionner. Supprimées progressivement en Phase 4.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Menu contextuel sur l'en-tête horizontal : « Sélectionner la colonne »
        # (repli souris du raccourci clavier Ctrl/Cmd+Espace). Le clic GAUCHE
        # sur l'en-tête reste réservé au tri (géré par table_controller).
        header = self.horizontalHeader()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

    # ── Colonne figée à droite ───────────────────────────────────────────────

    def freeze_right_column(self, col: int, delegate=None):
        """Fige la colonne `col` à droite, hors scroll horizontal.

        Crée une vue secondaire superposée sur le bord droit du tableau.
        Le viewport est placé EN DESSOUS via stackUnder() pour que la vue
        figée reste visible. Sync scroll vertical bidirectionnel.
        """
        self._frozen_col = col
        self._frozen_col_width = self.columnWidth(col)

        # Vue secondaire partagée
        frozen = QTableView(self)
        frozen.setModel(self.model())
        frozen.setSelectionModel(self.selectionModel())

        frozen.setFocusPolicy(Qt.NoFocus)
        frozen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        from PyQt5.QtWidgets import QFrame
        frozen.setFrameShape(QFrame.NoFrame)
        frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        frozen.verticalHeader().hide()
        frozen.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)

        if delegate:
            frozen.setItemDelegateForColumn(col, delegate)

        # N'afficher que la colonne figée
        self._apply_frozen_col_visibility(frozen, col)

        # Masquer dans la vue principale
        self.hideColumn(col)

        # Sync scroll vertical bidirectionnel
        self.verticalScrollBar().valueChanged.connect(frozen.verticalScrollBar().setValue)
        frozen.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)

        # Ré-appliquer la visibilité après reset du modèle (load_records)
        self.model().modelReset.connect(lambda: self._apply_frozen_col_visibility(frozen, col))
        self.model().modelReset.connect(lambda: self.hideColumn(col))

        self._frozen_view = frozen
        # Réserver col_w + vsb_w pixels à droite pour la colonne figée et l'ascenseur
        vsb_w = self.verticalScrollBar().sizeHint().width()
        self.setViewportMargins(0, 0, self._frozen_col_width + vsb_w, 0)
        # Clé : mettre le viewport EN DESSOUS de la vue figée (z-order correct)
        self.viewport().stackUnder(frozen)
        # Recalcul de la géométrie après initialisation du layout
        QTimer.singleShot(0, self._update_frozen_geometry)

    def _apply_frozen_col_visibility(self, frozen_view: QTableView, frozen_col: int):
        """Masque toutes les colonnes sauf frozen_col dans frozen_view."""
        model = self.model()
        if model is None:
            return
        for c in range(model.columnCount()):
            if c != frozen_col:
                frozen_view.hideColumn(c)
            else:
                frozen_view.showColumn(c)
        frozen_view.setColumnWidth(frozen_col, self._frozen_col_width)

    def _update_frozen_geometry(self):
        """Repositionne la vue figée au bord droit du tableau.

        x = self.width() - fw - col_w correspond exactement au bord droit du
        viewport après setViewportMargins(0, 0, col_w, 0), indépendamment du
        moment où la marge est appliquée par le layout.
        """
        if not hasattr(self, '_frozen_view') or not hasattr(self, '_frozen_col_width'):
            return
        col_w = self._frozen_col_width
        fw = self.frameWidth()
        vsb_w = self.verticalScrollBar().sizeHint().width()
        x = self.width() - fw - col_w - vsb_w
        y = fw
        w = col_w
        h = self.viewport().height() + self.horizontalHeader().height()
        self._frozen_view.setGeometry(x, y, w, h)
        self._frozen_view.setColumnWidth(self._frozen_col, col_w)
        self._frozen_view.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_frozen_geometry()

    def paintEvent(self, event):
        """Affiche un message centré quand le modèle est vide."""
        super().paintEvent(event)
        if self.model() and self.model().rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.save()
            font = QFont()
            font.setPointSize(13)
            painter.setFont(font)
            painter.setPen(QColor(160, 160, 160))
            search_term = getattr(self.model(), '_search_term', None)
            if search_term and isinstance(search_term, str):
                msg = f"Aucun résultat pour « {search_term} »"
            elif search_term and isinstance(search_term, dict):
                original = search_term.get('original', '')
                msg = f"Aucun résultat pour « {original} »" if original else "Aucun résultat"
            else:
                msg = "Aucun résultat"
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, msg)
            painter.restore()

    def keyPressEvent(self, event: QKeyEvent):
        """Gestion des événements clavier — miroir de CustomTableWidget."""
        key = event.key()
        model = self.model()

        # Delete / Backspace — efface les cellules sélectionnées éditables
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            sel_indexes = self.selectionModel().selectedIndexes() if self.selectionModel() else []
            if sel_indexes:
                main_window = getattr(self, 'main_window', None)
                save_service = getattr(main_window, 'event_driven_save_service', None)

                # Regrouper les sauvegardes en une seule transaction : sur une
                # sélection de plusieurs milliers de cellules, un commit SQLite
                # par cellule gèle l'interface plusieurs secondes.
                if save_service is not None:
                    main_window._bulk_edit_collector = set()

                for index in sel_indexes:
                    if model and model.flags(index) & Qt.ItemIsEditable:
                        model.setData(index, "", Qt.EditRole)

                if save_service is not None:
                    collector = main_window._bulk_edit_collector
                    main_window._bulk_edit_collector = None
                    if collector:
                        save_service.save_cells_batch_immediate(collector)
            return

        # Cmd+D (macOS) / Ctrl+D (Windows/Linux) — popup auto-complétion
        # Non applicable sur Référence Modèle (col 2) et Référence Commerciale (col 3)
        is_cmd = event.modifiers() & (Qt.MetaModifier | Qt.ControlModifier)
        if is_cmd and key == Qt.Key_D:
            if self.currentIndex().column() in {2, 3}:
                return
            parent = self.parent()
            while parent:
                if hasattr(parent, '_show_column_values_list'):
                    parent._show_column_values_list()
                    return
                parent = parent.parent()
            return

        # Entrée / Return — passe à la ligne suivante (même colonne)
        if key in (Qt.Key_Return, Qt.Key_Enter):
            idx = self.currentIndex()
            if idx.isValid() and model:
                next_row = idx.row() + 1
                if next_row < model.rowCount():
                    self.setCurrentIndex(model.index(next_row, idx.column()))
                    self.setFocus()
            return

        # F2 — ouvre l'éditeur, curseur en fin de texte (contenu préservé)
        if key == Qt.Key_F2:
            idx = self.currentIndex()
            if idx.isValid() and model and model.flags(idx) & Qt.ItemIsEditable:
                self.edit(idx)
            return

        # ── Raccourcis tableur : copie / sélection colonne-ligne / extension ──
        # (placés AVANT le bloc « frappe sur cellule vide » : Maj+Espace produit
        # un event.text()=" " printable qui sinon insérerait un espace)
        mods = event.modifiers()

        # Ctrl/Cmd+C — copier la sélection au presse-papiers (TSV, collable Excel)
        if is_cmd and key == Qt.Key_C and not (mods & Qt.ShiftModifier):
            self._copy_selection_to_clipboard()
            return

        # Espace : Ctrl/Cmd → sélectionne la colonne · Maj → sélectionne la ligne
        if key == Qt.Key_Space:
            if is_cmd:
                self._select_current_column()
                return
            if mods & Qt.ShiftModifier:
                self._select_current_row()
                return

        # Ctrl/Cmd+Maj+flèche — étendre la sélection jusqu'au bord
        if is_cmd and (mods & Qt.ShiftModifier) and key in (
                Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            self._extend_selection_to_edge(key)
            return

        # Frappe sur cellule vide → ouvre l'éditeur et insère le caractère
        if (event.text() and event.text()[0].isprintable()
                and not (event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier | Qt.AltModifier))):
            idx = self.currentIndex()
            if idx.isValid() and model and model.flags(idx) & Qt.ItemIsEditable:
                cell_value = model.data(idx, Qt.DisplayRole) or ""
                if not cell_value:
                    char = event.text()
                    if idx.column() in {0, 1}:   # Type et Fabricant → popup Cmd+D pré-filtrée
                        parent = self.parent()
                        while parent:
                            if hasattr(parent, '_show_column_values_list'):
                                parent._show_column_values_list(prefill=char)
                                return
                            parent = parent.parent()
                        return
                    # Autres colonnes vides → éditeur direct
                    self._pending_key_char = char
                    self.edit(idx)
                    QTimer.singleShot(0, self._init_editor_with_char)
                    return

        super().keyPressEvent(event)

    # ── Raccourcis tableur : copie / sélection / extension ───────────────────

    def _copy_selection_to_clipboard(self):
        """Copier la sélection au presse-papiers en TSV (collable dans Excel).

        Copie le rectangle englobant de la sélection : tabulations entre
        colonnes, sauts de ligne entre lignes, cellules non sélectionnées
        laissées vides (comme Excel). Les colonnes masquées sont ignorées.
        """
        sm = self.selectionModel()
        model = self.model()
        if sm is None or model is None:
            return
        indexes = sm.selectedIndexes()
        if not indexes:
            return
        rows = [i.row() for i in indexes]
        cols = [i.column() for i in indexes]
        r0, r1 = min(rows), max(rows)
        c0, c1 = min(cols), max(cols)
        visible_cols = [c for c in range(c0, c1 + 1) if not self.isColumnHidden(c)]
        selected = {(i.row(), i.column()) for i in indexes}
        lines = []
        for r in range(r0, r1 + 1):
            cells = []
            for c in visible_cols:
                if (r, c) in selected:
                    val = model.data(model.index(r, c), Qt.DisplayRole)
                    cells.append("" if val is None else str(val))
                else:
                    cells.append("")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))

    def select_column(self, col: int):
        """Sélectionner toute la colonne `col` (utilisé par le clavier et le menu en-tête)."""
        sm = self.selectionModel()
        model = self.model()
        if sm is None or model is None or col < 0 or model.rowCount() == 0:
            return
        top = model.index(0, col)
        bottom = model.index(model.rowCount() - 1, col)
        sm.select(QItemSelection(top, bottom), QItemSelectionModel.ClearAndSelect)
        # NoUpdate : déplace le curseur sans relancer une commande de sélection
        # (self.setCurrentIndex effacerait la plage qu'on vient de sélectionner)
        sm.setCurrentIndex(top, QItemSelectionModel.NoUpdate)

    def _select_current_column(self):
        """Sélectionner la colonne de la cellule courante (Ctrl/Cmd+Espace)."""
        idx = self.currentIndex()
        if idx.isValid():
            self.select_column(idx.column())

    def _select_current_row(self):
        """Sélectionner la ligne de la cellule courante (Maj+Espace)."""
        sm = self.selectionModel()
        model = self.model()
        idx = self.currentIndex()
        if sm is None or model is None or not idx.isValid():
            return
        left = model.index(idx.row(), 0)
        right = model.index(idx.row(), model.columnCount() - 1)
        sm.select(QItemSelection(left, right), QItemSelectionModel.ClearAndSelect)

    def _extend_selection_to_edge(self, key):
        """Étendre la sélection façon tableur (Ctrl/Cmd+Maj+flèche).

        Vertical (↑/↓) : s'arrête au bord du bloc de données (transition
        plein↔vide dans la colonne), exactement comme Cmd+↑/↓ (smart-navigate) ;
        à défaut de transition, va jusqu'à l'extrémité.
        Horizontal (←/→) : étend jusqu'à la première/dernière colonne.
        """
        sm = self.selectionModel()
        model = self.model()
        cur = self.currentIndex()
        if sm is None or model is None or not cur.isValid():
            return
        if key in (Qt.Key_Down, Qt.Key_Up):
            step = 1 if key == Qt.Key_Down else -1
            target_row = self._smart_vertical_target_row(cur.row(), cur.column(), step)
            if target_row is None:
                target_row = (model.rowCount() - 1) if step == 1 else 0
            target = model.index(target_row, cur.column())
        elif key == Qt.Key_Right:
            target = model.index(cur.row(), model.columnCount() - 1)
        else:  # Qt.Key_Left
            target = model.index(cur.row(), 0)
        sm.select(QItemSelection(cur, target), QItemSelectionModel.ClearAndSelect)
        # NoUpdate : conserve la plage étendue tout en déplaçant le curseur au bord
        sm.setCurrentIndex(target, QItemSelectionModel.NoUpdate)
        self.scrollTo(target)

    def _smart_vertical_target_row(self, row: int, col: int, step: int):
        """Ligne de bord de bloc dans la colonne `col` depuis `row`, en suivant
        `step` (+1 bas / -1 haut). Réplique navigate_to_empty_cell : s'arrête à
        la première transition plein↔vide. Retourne None si aucune transition
        jusqu'au bord (l'appelant ira alors à l'extrémité)."""
        model = self.model()
        n = model.rowCount()

        def is_empty(r: int) -> bool:
            val = model.data(model.index(r, col), Qt.DisplayRole)
            return val is None or str(val).strip() == ""

        cur_empty = is_empty(row)
        r = row + step
        while 0 <= r < n:
            if is_empty(r) != cur_empty:
                return r
            r += step
        return None

    def _on_header_context_menu(self, pos):
        """Menu contextuel de l'en-tête : « Sélectionner la colonne »."""
        header = self.horizontalHeader()
        col = header.logicalIndexAt(pos)
        if col < 0:
            return
        menu = QMenu(self)
        action_select = menu.addAction("Sélectionner la colonne")
        chosen = menu.exec_(header.mapToGlobal(pos))
        if chosen is action_select:
            self.select_column(col)

    def keyboardSearch(self, search: str):
        """Désactiver la navigation type-ahead native de QAbstractItemView."""
        pass

    def _init_editor_with_char(self):
        """Injecte le caractère en attente dans le QLineEdit éditeur actif."""
        from PyQt5.QtWidgets import QLineEdit
        char = getattr(self, '_pending_key_char', None)
        self._pending_key_char = None
        if char is None:
            return
        fw = self.focusWidget()
        if isinstance(fw, QLineEdit):
            fw.setText(char)
            fw.setCursorPosition(len(char))

    def mousePressEvent(self, event):
        """Clic simple sur la cellule courante → ouvre l'éditeur (Option B)."""
        from PyQt5.QtCore import Qt as _Qt
        if event.button() == _Qt.LeftButton:
            idx = self.indexAt(event.pos())
            if (idx.isValid()
                    and idx == self.currentIndex()
                    and self.model()
                    and self.model().flags(idx) & _Qt.ItemIsEditable):
                self.edit(idx)
        super().mousePressEvent(event)

    # ── Helpers de rétro-compatibilité ──────────────────────────────────────
    # Permettent aux services existants de continuer à fonctionner en Phase 3
    # avant que chaque service soit migré un par un (Phase 4).

    def currentRow(self) -> int:
        """Compat QTableWidget.currentRow()."""
        return self.currentIndex().row()

    def currentColumn(self) -> int:
        """Compat QTableWidget.currentColumn()."""
        return self.currentIndex().column()

    def rowCount(self) -> int:
        """Compat QTableWidget.rowCount()."""
        return self.model().rowCount() if self.model() else 0

    def columnCount(self) -> int:
        """Compat QTableWidget.columnCount()."""
        return self.model().columnCount() if self.model() else 0

    def selectedRanges(self) -> list:
        """Compat QTableWidget.selectedRanges() — retourne un _SelectionRangeCompat.

        Permet à tout code qui itère sur selectedRanges() et appelle
        .topRow()/.bottomRow()/.leftColumn()/.rightColumn() de fonctionner
        sans modification.
        """
        sm = self.selectionModel()
        if not sm or not sm.hasSelection():
            return []
        indexes = sm.selectedIndexes()
        if not indexes:
            return []
        rows = [idx.row() for idx in indexes]
        cols = [idx.column() for idx in indexes]
        return [_SelectionRangeCompat(min(rows), min(cols), max(rows), max(cols))]

    def horizontalHeaderItem(self, col: int):
        """Compat QTableWidget.horizontalHeaderItem() — retourne un QTableWidgetItem simulé."""
        if self.model():
            text = self.model().headerData(col, Qt.Horizontal, Qt.DisplayRole)
            if text is not None:
                return QTableWidgetItem(str(text))
        return None

    def item(self, row: int, col: int):
        """Compat QTableWidget.item() — retourne un QTableWidgetItem simulé depuis le modèle."""
        model = self.model()
        if not model:
            return None
        idx = model.index(row, col)
        if not idx.isValid():
            return None
        text = model.data(idx, Qt.DisplayRole) or ""
        db_id = model.data(idx, Qt.UserRole)
        widget_item = QTableWidgetItem(str(text))
        if db_id is not None:
            widget_item.setData(Qt.UserRole, db_id)
        return widget_item

    def visualItemRect(self, item):
        """Compat QTableWidget.visualItemRect() — stub, retourne QRect invalide.
        Le code qui en dépend (drag handle) a déjà une branche USE_TABLE_VIEW
        qui utilise visualRect(model_index) directement.
        """
        from PyQt5.QtCore import QRect
        return QRect()

    def setItem(self, row: int, col: int, item) -> None:
        """Compat QTableWidget.setItem() — écrit dans le modèle via setData()."""
        model = self.model()
        if not model:
            return
        idx = model.index(row, col)
        if idx.isValid():
            model.setData(idx, item.text() if item else "", Qt.EditRole)
            # Propager le UserRole (db_id) si présent
            if item and item.data(Qt.UserRole) is not None:
                model.setData(idx, item.data(Qt.UserRole), Qt.UserRole)

    def verticalHeaderItem(self, row: int):
        """Compat QTableWidget.verticalHeaderItem() — retourne un item avec numéro 1-indexé."""
        model = self.model()
        if model and 0 <= row < model.rowCount():
            return QTableWidgetItem(str(row + 1))
        return None

    def currentItem(self):
        """Compat QTableWidget.currentItem() — retourne un QTableWidgetItem simulé."""
        return self.item(self.currentRow(), self.currentColumn())

    def setCurrentCell(self, row: int, col: int) -> None:
        """Compat QTableWidget.setCurrentCell()."""
        model = self.model()
        if model:
            self.setCurrentIndex(model.index(row, col))

    def setVerticalHeaderItem(self, row: int, item) -> None:
        """Compat QTableWidget.setVerticalHeaderItem() — no-op.

        En mode QTableView les headers de ligne sont gérés par
        AppareillsTableModel.headerData() (Qt.Vertical). Aucune action nécessaire.
        """
        pass

    def selectedItems(self) -> list:
        """Compat QTableWidget.selectedItems() — retourne des QTableWidgetItem simulés.

        Permet à tout code qui itère sur selectedItems() et appelle .row()
        de continuer à fonctionner sans modification.
        """
        sm = self.selectionModel()
        if not sm:
            return []
        result = []
        for idx in sm.selectedIndexes():
            item = QTableWidgetItem(self.model().data(idx, Qt.DisplayRole) or "")
            # Stocker row/column dans l'item via sous-classe serait plus propre,
            # mais QTableWidgetItem expose row()/column() seulement si attaché à
            # un QTableWidget. On retourne donc un objet proxy léger.
            item._compat_row = idx.row()
            item._compat_col = idx.column()
            # Monkey-patch row() pour que item.row() fonctionne
            item.row = lambda r=idx.row(): r
            item.column = lambda c=idx.column(): c
            result.append(item)
        return result

    def setRangeSelected(self, selection_range, select: bool) -> None:
        """Compat QTableWidget.setRangeSelected() — traduit en QItemSelection pour QTableView.

        selection_range peut être un QTableWidgetSelectionRange ou un _SelectionRangeCompat,
        les deux exposent topRow/bottomRow/leftColumn/rightColumn.
        """
        from PyQt5.QtCore import QItemSelection
        from PyQt5.QtWidgets import QAbstractItemView
        model = self.model()
        sm = self.selectionModel()
        if not model or not sm:
            return
        top_left = model.index(selection_range.topRow(), selection_range.leftColumn())
        bottom_right = model.index(selection_range.bottomRow(), selection_range.rightColumn())
        if not top_left.isValid() or not bottom_right.isValid():
            return
        item_selection = QItemSelection(top_left, bottom_right)
        from PyQt5.QtCore import QItemSelectionModel
        flag = QItemSelectionModel.Select if select else QItemSelectionModel.Deselect
        sm.select(item_selection, flag)
