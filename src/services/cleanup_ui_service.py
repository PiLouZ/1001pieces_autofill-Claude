"""
Service d'interface utilisateur pour le nettoyage des doublons
Centralise la logique d'affichage et d'interaction pour la prévisualisation de nettoyage
"""

from typing import Dict, List, Any, Optional
import qtawesome as qta
from ..ui.qt_imports import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QGroupBox, QTabWidget,
    QProgressBar, QCheckBox, QTreeWidget, QTreeWidgetItem, QApplication, QMessageBox,
    QSize
)
from ..ui.qt_imports import Qt, QObject, pyqtSignal
from ..ui.qt_imports import QFont, QKeyEvent

from ..core.logger import app_logger
from .duplicates_analysis_service import clean_display_text
from .base_service import BaseService, safe_operation, service_operation

class KeyboardTreeWidget(QTreeWidget):
    """QTreeWidget personnalisé avec gestion clavier pour sélection par barre espace"""

    def keyPressEvent(self, event: QKeyEvent):
        """Gérer les événements clavier"""
        if event.key() == Qt.Key_Space:
            # Basculer l'état de la checkbox de l'élément sélectionné
            current_item = self.currentItem()
            if current_item and current_item.flags() & Qt.ItemIsUserCheckable:
                # Vérifier que c'est un appareil (pas un groupe)
                if current_item.parent() is not None:  # C'est un enfant (appareil)
                    current_state = current_item.checkState(0)
                    new_state = Qt.Unchecked if current_state == Qt.Checked else Qt.Checked
                    current_item.setCheckState(0, new_state)
                    event.accept()
                    return

        # Pour toutes les autres touches, comportement par défaut
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        """Gérer le menu contextuel.

        - Sur un appareil (item enfant) : action « Copier » de la cellule.
        - Sur un groupe parent : action déléguée via le callback optionnel
          `on_group_context_menu(group_item)` posé par le widget propriétaire
          (sert au marquage « distinct » depuis l'arbre des appareils).
        """
        item = self.itemAt(event.pos())
        if not item:
            return

        from ..ui.qt_imports import QMenu, QAction

        if item.parent() is not None:  # C'est un appareil (pas un groupe)
            menu = QMenu(self)
            copy_action = QAction("Copier", self)
            copy_action.triggered.connect(lambda: self._copy_cell_value(item, self.currentColumn()))
            menu.addAction(copy_action)
            menu.exec_(event.globalPos())
            return

        # Item parent (groupe) : déléguer au callback si présent
        on_group = getattr(self, 'on_group_context_menu', None)
        if callable(on_group):
            menu = QMenu(self)
            distinct_action = QAction("Marquer ce groupe comme distinct (faux doublon)", self)
            distinct_action.triggered.connect(lambda: on_group(item))
            menu.addAction(distinct_action)
            menu.exec_(event.globalPos())

    def _copy_cell_value(self, item, column):
        """Copier la valeur d'une cellule dans le presse-papier"""
        if item and 0 <= column < item.columnCount():
            text = item.text(column)
            if text:
                from ..ui.qt_imports import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
                app_logger.info(f"Valeur copiée: {text}")

class CleanupStatsWidget(QWidget):
    """Widget pour afficher les statistiques de nettoyage"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """Initialiser l'interface du widget statistiques"""
        layout = QHBoxLayout(self)
        
        # Statistiques principales
        self.devices_stats = QLabel("0 groupes d'appareils (0 appareils concernés)")
        self.pieces_stats = QLabel("0 pièces dupliquées")
        self.inconsistencies_stats = QLabel("0 incohérences potentielles")
        self.savings_stats = QLabel("Économie potentielle : 0 appareils, 0 pièces")

        # Style
        for label in [self.devices_stats, self.pieces_stats, self.inconsistencies_stats, self.savings_stats]:
            label.setStyleSheet(
                "padding: 5px 8px; background: #f8f9fa; border-radius: 4px; margin: 2px;"
                " color: #495057; font-size: 11px;"
            )
            
        layout.addWidget(self.devices_stats)
        layout.addWidget(self.pieces_stats)
        layout.addWidget(self.inconsistencies_stats)
        layout.addWidget(self.savings_stats)
        
    def update_stats(self, statistics: Dict[str, Any]):
        """Mettre à jour les statistiques affichées"""
        self.devices_stats.setText(
            f"{statistics.get('total_duplicate_devices', 0)} groupes "
            f"({statistics.get('total_affected_devices', 0)} appareils concernés)"
        )

        self.pieces_stats.setText(
            f"{statistics.get('total_duplicate_pieces', 0)} pièces dupliquées "
            f"({statistics.get('total_affected_pieces', 0)} occurrences)"
        )

        self.inconsistencies_stats.setText(
            f"{statistics.get('total_potential_inconsistencies', 0)} incohérences potentielles"
        )

        self.savings_stats.setText(
            f"Économie potentielle : {statistics.get('potential_savings_devices', 0)} appareils, "
            f"{statistics.get('potential_savings_pieces', 0)} pièces"
        )

class DuplicateDevicesWidget(QWidget):
    """Widget pour gérer les appareils en doublon"""
    
    devices_selection_changed = pyqtSignal()
    # Émis après marquage "distinct" d'un ou plusieurs groupes : porte la liste
    # [{'ref_modele': str, 'affected': int, 'savings': int}, …] pour que le dialogue
    # décrémente les stats live et rafraîchisse l'onglet "Références distinctes".
    groups_marked_distinct = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duplicate_groups = []
        self.history_callback = None  # Callback pour enregistrer dans l'historique
        self.init_ui()
        
    def init_ui(self):
        """Initialiser l'interface pour les appareils en doublon"""
        layout = QVBoxLayout(self)

        # Bandeau d'aide : lever l'ambiguïté "coché = conservé" (et non supprimé)
        help_label = QLabel(
            "Cochez l'appareil à CONSERVER dans chaque groupe — il recevra les pièces "
            "des autres, qui seront supprimés. Sélectionnez un ou plusieurs groupes "
            "(Ctrl/Maj-clic) pour les marquer comme faux doublons (« distincts »)."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            "font-size: 11px; padding: 6px 10px; color: #495057;"
            " background-color: #e7f3ff; border-radius: 4px;"
        )
        layout.addWidget(help_label)

        # En-tête avec actions
        header_layout = QHBoxLayout()
        
        _compact_style = (
            "QPushButton { padding: 2px 8px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }"
        )

        self.select_all_btn = QPushButton("Tout sélectionner")
        self.select_all_btn.setStyleSheet(_compact_style)
        self.select_none_btn = QPushButton("Tout désélectionner")
        self.select_none_btn.setStyleSheet(_compact_style)
        self.auto_select_most_pieces_btn = QPushButton("Auto (+ de pièces)")
        self.auto_select_most_pieces_btn.setToolTip("Sélectionner automatiquement l'appareil avec le plus de pièces")
        self.auto_select_most_pieces_btn.setStyleSheet(_compact_style)
        self.auto_select_newest_btn = QPushButton("Auto (+ récents)")
        self.auto_select_newest_btn.setToolTip("Sélectionner automatiquement les appareils les plus récents")
        self.auto_select_newest_btn.setStyleSheet(_compact_style)

        # Boutons pour décisions sur doublons
        self.mark_distinct_btn = QPushButton("Marquer comme distinct(s)")
        self.mark_distinct_btn.setToolTip(
            "Marquer le(s) groupe(s) sélectionné(s) comme faux doublons "
            "(Ctrl/Maj-clic pour en sélectionner plusieurs)"
        )
        self.mark_distinct_btn.setIcon(qta.icon('fa5s.check-double', color='white'))
        self.mark_distinct_btn.setIconSize(QSize(11, 11))
        self.mark_distinct_btn.setStyleSheet(
            "QPushButton { background-color: #28a745; color: white; font-weight: bold;"
            " padding: 2px 8px; font-size: 11px; border-radius: 3px; }"
        )
        self.mark_distinct_btn.setEnabled(False)

        header_layout.addWidget(self.select_all_btn)
        header_layout.addWidget(self.select_none_btn)
        header_layout.addWidget(self.auto_select_most_pieces_btn)
        header_layout.addWidget(self.auto_select_newest_btn)
        header_layout.addWidget(self.mark_distinct_btn)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Arbre des appareils avec gestion clavier
        self.devices_tree = KeyboardTreeWidget()
        self.devices_tree.setHeaderLabels([
            "Maître (à conserver)", "ID", "Référence Modèle", "Type", "Fabricant",
            "Référence Commerciale", "Autre Référence", "Nb Pièces"
        ])
        self.devices_tree.setRootIsDecorated(True)
        # Multi-sélection de lignes : permet de marquer plusieurs groupes "distincts"
        # en une action (Ctrl/Shift-clic). N'affecte pas les checkboxes de fusion
        # (colonne 0), qui restent indépendantes de la sélection de ligne.
        self.devices_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)

        layout.addWidget(self.devices_tree)
        
        # Connecter les signaux
        self.devices_tree.itemChanged.connect(self._on_item_changed)
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_none_btn.clicked.connect(self._select_none)
        self.auto_select_most_pieces_btn.clicked.connect(self._auto_select_most_pieces)
        self.auto_select_newest_btn.clicked.connect(self._auto_select_newest)
        self.mark_distinct_btn.clicked.connect(self._mark_selected_as_distinct)
        self.devices_tree.itemSelectionChanged.connect(self._update_buttons_state)
        # Clic droit sur un groupe parent : marquer ce groupe comme distinct
        self.devices_tree.on_group_context_menu = self._on_group_context_distinct
        
    def populate_devices(self, duplicate_devices: List[Dict[str, Any]]):
        """Remplir la liste des appareils en doublon"""
        self.duplicate_groups = duplicate_devices
        self.devices_tree.clear()
        
        for group in duplicate_devices:
            ref_modele = group['ref_modele']
            count = group['count']
            devices = group['devices']
            
            # Créer le nœud parent pour le groupe
            group_item = QTreeWidgetItem([
                "", "", f"{ref_modele} ({count} appareils)", "", "", "", "", ""
            ])
            group_item.setExpanded(True)
            
            # Style pour le groupe
            font = QFont()
            font.setBold(True)
            group_item.setFont(2, font)
            
            self.devices_tree.addTopLevelItem(group_item)
            
            # Ajouter les appareils individuels
            for device in devices:
                device_item = QTreeWidgetItem([
                    "", str(device['id']), device['ref_modele'],
                    device['type_appareil'], device['manufacturer'],
                    device['commercial_ref'], device.get('other_ref', ''),
                    str(device['pieces_count'])
                ])
                
                # Checkbox pour sélection
                device_item.setFlags(device_item.flags() | Qt.ItemIsUserCheckable)
                device_item.setCheckState(0, Qt.Unchecked)
                device_item.setData(0, Qt.UserRole, device['id'])
                
                group_item.addChild(device_item)
                
        # Ajuster les colonnes
        for i in range(self.devices_tree.columnCount()):
            self.devices_tree.resizeColumnToContents(i)

        # Forcer l'expansion de tous les groupes pour voir tous les appareils
        self.devices_tree.expandAll()

        # Indiquer la validité de fusion de chaque groupe (0/1/≥2 maîtres cochés)
        self._refresh_group_validity()

    def _on_item_changed(self, item, column):
        """Gérer les changements de sélection"""
        if column == 0:  # Colonne checkbox (désignation du maître)
            self.devices_selection_changed.emit()
            self._refresh_group_validity()

    def _refresh_group_validity(self):
        """Marquer visuellement chaque groupe selon le nombre de maîtres cochés.

        Une fusion exige exactement 1 appareil coché par groupe ; 0 ou ≥2 rend le
        groupe ignoré silencieusement par `get_merge_groups()`. On le signale par
        une icône en tête de groupe. `blockSignals` évite la récursion
        setIcon → itemChanged → _on_item_changed.
        """
        tree = self.devices_tree
        blocked = tree.blockSignals(True)
        try:
            root = tree.invisibleRootItem()
            for i in range(root.childCount()):
                group_item = root.child(i)
                checked = sum(
                    1 for j in range(group_item.childCount())
                    if group_item.child(j).checkState(0) == Qt.Checked
                )
                if checked == 1:
                    group_item.setIcon(0, qta.icon('fa5s.check-circle', color='#28a745'))
                    group_item.setToolTip(0, "Prêt à fusionner : 1 maître désigné")
                elif checked == 0:
                    group_item.setIcon(0, qta.icon('fa5s.minus-circle', color='#adb5bd'))
                    group_item.setToolTip(0, "Aucun maître coché — ce groupe sera ignoré au nettoyage")
                else:
                    group_item.setIcon(0, qta.icon('fa5s.exclamation-triangle', color='#dc3545'))
                    group_item.setToolTip(
                        0, f"{checked} appareils cochés — fusion impossible (1 seul maître attendu)"
                    )
        finally:
            tree.blockSignals(blocked)


    def _select_all(self):
        """Sélectionner tous les appareils"""
        self._set_all_checkboxes(Qt.Checked)
        
    def _select_none(self):
        """Désélectionner tous les appareils"""
        self._set_all_checkboxes(Qt.Unchecked)
        
    def _set_all_checkboxes(self, state):
        """Définir l'état de toutes les checkboxes"""
        root = self.devices_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                device_item.setCheckState(0, state)
                
    def _auto_select_most_pieces(self):
        """Sélectionner automatiquement les appareils avec le plus de pièces associées"""
        root = self.devices_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)

            # Trouver l'appareil avec le plus de pièces
            best_item = None
            max_pieces = -1

            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                pieces_count = int(device_item.text(7) or 0)  # Colonne "Nb Pièces"
                if pieces_count > max_pieces:
                    max_pieces = pieces_count
                    best_item = device_item

            # Si aucun appareil n'a de pièces, prendre le premier
            if best_item is None and group_item.childCount() > 0:
                best_item = group_item.child(0)

            # Sélectionner celui avec le plus de pièces comme maître (coché)
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                if device_item == best_item:
                    device_item.setCheckState(0, Qt.Checked)    # Celui avec plus de pièces devient maître
                else:
                    device_item.setCheckState(0, Qt.Unchecked)  # Les autres ne sont pas sélectionnés
                    
    def _auto_select_newest(self):
        """Sélectionner automatiquement les appareils les plus récents (ID plus grands)"""
        root = self.devices_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)

            # Trouver l'appareil avec l'ID le plus grand (plus récent)
            newest_item = None
            newest_id = -1

            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                device_id = device_item.data(0, Qt.UserRole)
                if device_id and device_id > newest_id:
                    newest_id = device_id
                    newest_item = device_item

            # Si aucun ID trouvé, prendre le premier
            if newest_item is None and group_item.childCount() > 0:
                newest_item = group_item.child(0)

            # Sélectionner le plus récent comme maître (coché)
            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                if device_item == newest_item:
                    device_item.setCheckState(0, Qt.Checked)    # Le plus récent devient maître
                else:
                    device_item.setCheckState(0, Qt.Unchecked)  # Les autres ne sont pas sélectionnés
        
    def get_merge_groups(self) -> List[Dict[str, Any]]:
        """Obtenir les groupes de fusion d'appareils"""
        from ..core.config import Config

        merge_groups = []
        nb_doublons_a_supprimer = 0
        nb_sans_selection = 0
        root = self.devices_tree.invisibleRootItem()

        for i in range(root.childCount()):
            group_item = root.child(i)
            group_devices = []
            selected_devices = []

            for j in range(group_item.childCount()):
                device_item = group_item.child(j)
                device_id = device_item.data(0, Qt.UserRole)
                if device_id is not None:  # Vérifier que l'ID est valide
                    group_devices.append(device_id)

                    if device_item.checkState(0) == Qt.Checked:
                        selected_devices.append(device_id)

            # Comptage agrégé plutôt qu'une ligne par groupe (v3.66.0) : sur une base
            # de plusieurs centaines de milliers d'appareils, ces trois messages
            # produisaient des centaines de milliers de lignes par nettoyage.
            if Config.LOG_VERBOSE_PER_DEVICE:
                app_logger.debug(f"Groupe {i}: total={len(group_devices)}, sélectionnés={len(selected_devices)}")

            # S'il y a exactement UN appareil sélectionné, créer un groupe de fusion
            if len(selected_devices) == 1 and len(group_devices) > 1:
                # L'appareil sélectionné (coché) devient le maître qui reçoit les pièces
                master_id = selected_devices[0]
                # Les autres appareils du groupe sont les doublons à supprimer
                duplicate_ids = [d for d in group_devices if d != master_id]

                merge_groups.append({
                    'master_id': master_id,
                    'duplicate_ids': duplicate_ids
                })
                nb_doublons_a_supprimer += len(duplicate_ids)
                if Config.LOG_VERBOSE_PER_DEVICE:
                    app_logger.info(f"Groupe de fusion créé: maître={master_id} (sélectionné), doublons à supprimer={duplicate_ids}")
            elif len(selected_devices) > 1:
                # Conservé à l'unité : rare, actionnable, et bloque une fusion.
                app_logger.warning(f"Groupe {i}: Plus d'un appareil sélectionné - fusion impossible")
            elif len(selected_devices) == 0:
                nb_sans_selection += 1

        app_logger.info(
            f"Total groupes de fusion: {len(merge_groups)} "
            f"({nb_doublons_a_supprimer} doublons à supprimer, "
            f"{nb_sans_selection} groupes sans sélection)"
        )
        return merge_groups

    def _selected_groups(self) -> List[QTreeWidgetItem]:
        """Résoudre la sélection courante en groupes parents dédupliqués.

        La sélection peut contenir des groupes et/ou des appareils enfants ;
        chaque enfant est remonté à son groupe parent. La déduplication conserve
        l'ordre d'apparition dans l'arbre.
        """
        groups = []
        seen = set()
        for item in self.devices_tree.selectedItems():
            group_item = item.parent() if item.parent() else item
            if id(group_item) not in seen:
                seen.add(id(group_item))
                groups.append(group_item)
        return groups

    @staticmethod
    def _extract_ref_modele(group_item: QTreeWidgetItem) -> str:
        """Extraire la référence modèle du libellé d'un groupe ('REF (n appareils)')."""
        group_text = group_item.text(2)  # Colonne "Référence Modèle"
        return group_text.split(" (")[0] if " (" in group_text else group_text

    def _update_buttons_state(self):
        """Mettre à jour l'état des boutons selon la sélection"""
        # Le bouton "Marquer comme distinct(s)" est activé dès qu'au moins un groupe
        # est sélectionné (directement ou via un de ses appareils enfants).
        self.mark_distinct_btn.setEnabled(len(self._selected_groups()) > 0)

    def _mark_selected_as_distinct(self):
        """Marquer le(s) groupe(s) sélectionné(s) comme distinct(s) — en masse (bouton)."""
        app_logger.info("BOUTON 'Marquer comme distinct(s)' cliqué")
        group_items = self._selected_groups()
        if not group_items:
            app_logger.warning("Aucun groupe sélectionné pour marquage distinct")
            return
        self._apply_distinct_marking(group_items)

    def _on_group_context_distinct(self, group_item: QTreeWidgetItem):
        """Marquer un groupe comme distinct depuis le menu contextuel (clic droit)."""
        app_logger.info("MENU CONTEXTUEL 'Marquer ce groupe comme distinct'")
        if group_item is not None:
            self._apply_distinct_marking([group_item])

    def _apply_distinct_marking(self, group_items: List[QTreeWidgetItem]):
        """Cœur du marquage distinct : confirmation, écriture en base, retrait, signal.

        Partagé par le bouton (sélection multiple) et le menu contextuel (un groupe).
        """
        if not group_items:
            return

        # Confirmation : ce marquage est ENREGISTRÉ IMMÉDIATEMENT en base, hors du
        # cycle "Appliquer/Annuler" du nettoyage. L'utilisateur doit le savoir.
        nb = len(group_items)
        refs_apercu = ", ".join(self._extract_ref_modele(g) for g in group_items[:5])
        if nb > 5:
            refs_apercu += f", … (+{nb - 5})"
        reply = QMessageBox.question(
            self,
            "Marquage immédiat",
            f"Marquer {nb} {'groupe' if nb <= 1 else 'groupes'} comme distinct{'s' if nb > 1 else ''} ?\n\n"
            f"{refs_apercu}\n\n"
            "Attention — cette action est enregistrée immédiatement en base "
            "(elle ne passe pas par le bouton « Appliquer le nettoyage »).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Accéder au DatabaseManager via la chaîne de parents
        parent_widget = self.parent()
        while parent_widget and not hasattr(parent_widget, 'db_manager'):
            parent_widget = parent_widget.parent()

        if not (parent_widget and hasattr(parent_widget, 'db_manager')):
            app_logger.error("Impossible d'accéder au DatabaseManager")
            return

        db_manager = parent_widget.db_manager
        marked = []  # [{'ref_modele', 'affected', 'savings'}]
        root = self.devices_tree.invisibleRootItem()

        for group_item in group_items:
            ref_modele = self._extract_ref_modele(group_item)
            success = db_manager.save_reference_decision(
                ref_modele, 'DISTINCT', 'Marqué comme appareils distincts par l\'utilisateur'
            )
            if not success:
                app_logger.error(f"Échec marquage distinct pour {ref_modele}")
                continue

            app_logger.info(f"Groupe {ref_modele} marqué comme distinct")

            # Nombre d'appareils concernés par ce groupe (pour les stats live)
            affected = group_item.childCount()

            # Retrait immédiat du groupe de l'arbre (#3)
            index = root.indexOfChild(group_item)
            if index >= 0:
                root.takeChild(index)

            # Tenir à jour la liste interne des groupes
            self.duplicate_groups = [
                g for g in self.duplicate_groups if g.get('ref_modele') != ref_modele
            ]

            marked.append({
                'ref_modele': ref_modele,
                'affected': affected,
                'savings': max(affected - 1, 0),  # économie = doublons potentiels du groupe
            })

        if not marked:
            return

        # Historique : une entrée agrégée si plusieurs groupes, sinon unitaire
        if self.history_callback:
            if len(marked) == 1:
                self.history_callback(
                    "Marquage distinct",
                    f"Référence '{marked[0]['ref_modele']}' marquée comme distincte",
                    "Succès"
                )
            else:
                refs = ", ".join(m['ref_modele'] for m in marked)
                self.history_callback(
                    "Marquage distinct",
                    f"{len(marked)} références marquées comme distinctes : {refs}",
                    "Succès"
                )

        # Signaler au dialogue : décrément des stats + rafraîchissement de l'onglet distinctes
        self.groups_marked_distinct.emit(marked)
        self._update_buttons_state()

class DuplicatePiecesWidget(QWidget):
    """Widget pour gérer les pièces dupliquées"""

    pieces_selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duplicate_pieces = []
        self.init_ui()
        
    def init_ui(self):
        """Initialiser l'interface pour les pièces dupliquées"""
        layout = QVBoxLayout(self)
        
        # Actions
        _compact = (
            "QPushButton { padding: 2px 8px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }"
        )
        actions_layout = QHBoxLayout()
        self.select_all_pieces_btn = QPushButton("Tout sélectionner")
        self.select_all_pieces_btn.setStyleSheet(_compact)
        self.select_none_pieces_btn = QPushButton("Tout désélectionner")
        self.select_none_pieces_btn.setStyleSheet(_compact)

        actions_layout.addWidget(self.select_all_pieces_btn)
        actions_layout.addWidget(self.select_none_pieces_btn)
        actions_layout.addStretch()
        
        layout.addLayout(actions_layout)
        
        # Table des pièces
        self.pieces_table = QTableWidget()
        self.pieces_table.setColumnCount(3)
        self.pieces_table.setHorizontalHeaderLabels(["Supprimer", "Référence Pièce", "Nombre de doublons"])
        self.pieces_table.horizontalHeader().setStretchLastSection(True)
        # Tri par clic sur en-tête (ex. trier par nombre de doublons). Les cases sont
        # des items checkables (et non des QCheckBox en cellWidget) : la coche voyage
        # donc avec la ligne au tri, sans désynchronisation.
        self.pieces_table.setSortingEnabled(True)

        layout.addWidget(self.pieces_table)

        # Connecter les signaux
        self.select_all_pieces_btn.clicked.connect(self._select_all_pieces)
        self.select_none_pieces_btn.clicked.connect(self._select_none_pieces)
        self.pieces_table.itemChanged.connect(self._on_piece_item_changed)
        
    def populate_pieces(self, duplicate_pieces: List[Dict[str, Any]]):
        """Remplir la table des pièces dupliquées"""
        self.duplicate_pieces = duplicate_pieces
        # Désactiver le tri pendant le remplissage (sinon les lignes se réordonnent
        # à chaque insertion). Réactivé après.
        self.pieces_table.setSortingEnabled(False)
        self.pieces_table.setRowCount(len(duplicate_pieces))

        for row, piece_data in enumerate(duplicate_pieces):
            ref_piece = piece_data['ref_piece']
            count = piece_data['count']

            # Case à cocher = item checkable (colonne "Supprimer"). La coche voyage
            # avec la ligne au tri (contrairement à un QCheckBox en cellWidget).
            check_item = QTableWidgetItem()
            check_item.setFlags(
                (check_item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable
            )
            check_item.setCheckState(Qt.Unchecked)
            self.pieces_table.setItem(row, 0, check_item)

            # Référence pièce
            ref_item = QTableWidgetItem(ref_piece)
            ref_item.setFlags(ref_item.flags() & ~Qt.ItemIsEditable)
            self.pieces_table.setItem(row, 1, ref_item)

            # Nombre de doublons — donnée numérique pour un tri correct (10 > 9)
            count_item = QTableWidgetItem()
            count_item.setData(Qt.DisplayRole, int(count))
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            self.pieces_table.setItem(row, 2, count_item)

        self.pieces_table.setSortingEnabled(True)
        self.pieces_table.resizeColumnsToContents()

    def _on_piece_item_changed(self, item):
        """Émettre le signal de sélection quand une case (colonne 0) change."""
        if item.column() == 0:
            self.pieces_selection_changed.emit()

    def _set_all_pieces_checked(self, checked: bool):
        """Cocher/décocher toutes les pièces (un seul rafraîchissement de signal)."""
        state = Qt.Checked if checked else Qt.Unchecked
        table = self.pieces_table
        blocked = table.blockSignals(True)
        try:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item:
                    item.setCheckState(state)
        finally:
            table.blockSignals(blocked)
        self.pieces_selection_changed.emit()

    def _select_all_pieces(self):
        """Sélectionner toutes les pièces"""
        self._set_all_pieces_checked(True)

    def _select_none_pieces(self):
        """Désélectionner toutes les pièces"""
        self._set_all_pieces_checked(False)

    def get_selected_pieces(self) -> List[str]:
        """Obtenir les références des pièces sélectionnées"""
        selected = []
        for row in range(self.pieces_table.rowCount()):
            check_item = self.pieces_table.item(row, 0)
            if check_item and check_item.checkState() == Qt.Checked:
                ref_item = self.pieces_table.item(row, 1)
                if ref_item:
                    selected.append(ref_item.text())
        return selected

class CleanupUIService(BaseService):
    """Service d'interface utilisateur pour le nettoyage des doublons"""

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent_window, parent)
        
    def create_stats_widget(self) -> CleanupStatsWidget:
        """Créer le widget des statistiques"""
        return CleanupStatsWidget()
        
    def create_devices_widget(self) -> DuplicateDevicesWidget:
        """Créer le widget des appareils en doublon"""
        return DuplicateDevicesWidget()
        
    def create_pieces_widget(self) -> DuplicatePiecesWidget:
        """Créer le widget des pièces dupliquées"""
        return DuplicatePiecesWidget()

    def create_distinct_references_widget(self) -> 'DistinctReferencesWidget':
        """Créer le widget des références distinctes"""
        return DistinctReferencesWidget()

    def create_history_widget(self) -> 'ActionHistoryWidget':
        """Créer le widget de l'historique des actions"""
        return ActionHistoryWidget()

class DistinctReferencesWidget(QWidget):
    """Widget pour gérer les références marquées comme distinctes"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_manager = None
        self.distinct_references = []
        self.init_ui()

    def init_ui(self):
        """Initialiser l'interface pour les références distinctes"""
        layout = QVBoxLayout(self)

        # En-tête avec explication
        header_label = QLabel(
            "Références marquées comme distinctes — "
            "ces références ne seront plus proposées comme doublons potentiels."
        )
        header_label.setStyleSheet(
            "font-size: 11px; padding: 6px 10px; color: #495057;"
            " background-color: #e7f3ff; border-radius: 4px;"
        )
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        # Boutons d'action
        buttons_layout = QHBoxLayout()

        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(qta.icon('fa5s.sync-alt', color='#555555'))
        self.refresh_btn.setIconSize(QSize(13, 13))
        self.refresh_btn.setFixedSize(26, 26)
        self.refresh_btn.setFlat(True)
        self.refresh_btn.setToolTip("Actualiser")
        self.refresh_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; }"
            "QPushButton:hover { background: rgba(0,0,0,0.08); border-radius: 3px; }"
        )

        self.remove_btn = QPushButton("Retirer la sélection")
        self.remove_btn.setIcon(qta.icon('fa5s.trash-alt', color='white'))
        self.remove_btn.setIconSize(QSize(11, 11))
        self.remove_btn.setStyleSheet(
            "QPushButton { background-color: #dc3545; color: white; font-weight: bold;"
            " padding: 2px 8px; font-size: 11px; border-radius: 3px; }"
        )
        self.remove_btn.setEnabled(False)

        buttons_layout.addWidget(self.refresh_btn)
        buttons_layout.addWidget(self.remove_btn)
        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        # Table des références distinctes
        self.references_tree = KeyboardTreeWidget()
        self.references_tree.setHeaderLabels([
            "Sélection", "Référence Modèle", "Nb Appareils", "Date Marquage", "Action"
        ])
        self.references_tree.setRootIsDecorated(False)

        layout.addWidget(self.references_tree)

        # Connecter les signaux
        self.refresh_btn.clicked.connect(self.load_distinct_references)
        self.remove_btn.clicked.connect(self._remove_selected_references)
        self.references_tree.itemSelectionChanged.connect(self._update_buttons_state)

    def set_db_manager(self, db_manager):
        """Définir le gestionnaire de base de données"""
        self.db_manager = db_manager
        self.load_distinct_references()

    def load_distinct_references(self):
        """Charger les références marquées comme distinctes"""
        if not self.db_manager:
            return

        # Requête pour récupérer les références distinctes avec comptage des appareils
        query = """
            SELECT rd.ref_modele,
                   COUNT(a.id) as nb_appareils,
                   rd.created_at,
                   rd.ref_modele as ref_key
            FROM reference_decisions rd
            LEFT JOIN appareils a ON a.ref_modele = rd.ref_modele
            WHERE rd.decision = 'DISTINCT'
            GROUP BY rd.ref_modele, rd.created_at
            ORDER BY rd.created_at DESC
        """

        results = self.db_manager.execute_query(query)
        self.distinct_references = results or []

        # Peupler l'arbre
        self.references_tree.clear()

        for row in self.distinct_references:
            ref_modele = row[0]
            nb_appareils = row[1]
            created_at = row[2]
            ref_id = row[3]

            item = QTreeWidgetItem([
                "", ref_modele, str(nb_appareils),
                created_at or "Date inconnue", "Retirer"
            ])

            # Checkbox pour sélection
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            item.setData(0, Qt.UserRole, ref_modele)  # Utiliser ref_modele comme clé

            self.references_tree.addTopLevelItem(item)

        # Ajuster les colonnes
        for i in range(self.references_tree.columnCount()):
            self.references_tree.resizeColumnToContents(i)

        app_logger.info(f"Chargé {len(self.distinct_references)} références distinctes")

    def _update_buttons_state(self):
        """Mettre à jour l'état des boutons selon les sélections"""
        has_selection = False

        root = self.references_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.checkState(0) == Qt.Checked:
                has_selection = True
                break

        self.remove_btn.setEnabled(has_selection)

    def _remove_selected_references(self):
        """Retirer les références sélectionnées de la liste des distinctes"""
        if not self.db_manager:
            return

        # Récupérer les références sélectionnées
        selected_refs = []

        root = self.references_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.checkState(0) == Qt.Checked:
                ref_modele = item.data(0, Qt.UserRole)  # ref_modele stocké dans UserRole
                if ref_modele:
                    selected_refs.append(ref_modele)

        if not selected_refs:
            return

        # Confirmation
        reply = QMessageBox.question(
            self,
            "Confirmation de suppression",
            f"Êtes-vous sûr de vouloir retirer {len(selected_refs)} références "
            f"de la liste des références distinctes?\n\n"
            f"Ces références pourront à nouveau être proposées comme doublons potentiels.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Supprimer de la base de données
        placeholders = ','.join(['?'] * len(selected_refs))
        delete_query = f"DELETE FROM reference_decisions WHERE ref_modele IN ({placeholders})"

        result = self.db_manager.execute_custom_query(delete_query, selected_refs)
        success = True  # execute_custom_query n'a pas d'erreur si ça marche

        if success:
            self.load_distinct_references()
            QMessageBox.information(
                self,
                "Suppression réussie",
                f"{len(selected_refs)} références retirées avec succès.\n"
                f"Elles pourront à nouveau être détectées comme doublons potentiels."
            )
        else:
            QMessageBox.warning(self, "Erreur", "Erreur lors de la suppression des références.")

class ActionHistoryWidget(QWidget):
    """Widget pour afficher l'historique des actions de nettoyage"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_manager = None
        self.history_actions = []
        self.init_ui()

    def init_ui(self):
        """Initialiser l'interface pour l'historique"""
        layout = QVBoxLayout(self)

        # En-tête avec explication
        header_label = QLabel(
            "Historique des actions de nettoyage — "
            "synthèse de toutes les actions de fusion et nettoyage effectuées."
        )
        header_label.setStyleSheet(
            "font-size: 11px; padding: 6px 10px; color: #495057;"
            " background-color: #f8f9fa; border-radius: 4px;"
        )
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        _flat_btn_style = (
            "QPushButton { border: none; background: transparent; }"
            "QPushButton:hover { background: rgba(0,0,0,0.08); border-radius: 3px; }"
        )

        # Boutons d'action
        buttons_layout = QHBoxLayout()

        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(qta.icon('fa5s.sync-alt', color='#555555'))
        self.refresh_btn.setIconSize(QSize(13, 13))
        self.refresh_btn.setFixedSize(26, 26)
        self.refresh_btn.setFlat(True)
        self.refresh_btn.setToolTip("Actualiser")
        self.refresh_btn.setStyleSheet(_flat_btn_style)

        self.clear_btn = QPushButton("Vider l'historique")
        self.clear_btn.setIcon(qta.icon('fa5s.trash-alt', color='white'))
        self.clear_btn.setIconSize(QSize(11, 11))
        self.clear_btn.setStyleSheet(
            "QPushButton { background-color: #dc3545; color: white; font-weight: bold;"
            " padding: 2px 8px; font-size: 11px; border-radius: 3px; }"
        )

        self.export_btn = QPushButton("Exporter")
        self.export_btn.setIcon(qta.icon('fa5s.file-export', color='#555555'))
        self.export_btn.setIconSize(QSize(11, 11))
        self.export_btn.setStyleSheet(
            "QPushButton { padding: 2px 8px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 3px; }"
        )

        buttons_layout.addWidget(self.refresh_btn)
        buttons_layout.addWidget(self.clear_btn)
        buttons_layout.addWidget(self.export_btn)
        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        # Table de l'historique
        self.history_tree = KeyboardTreeWidget()
        self.history_tree.setHeaderLabels([
            "Date/Heure", "Action", "Détails", "Résultat", "Utilisateur"
        ])
        self.history_tree.setRootIsDecorated(False)

        layout.addWidget(self.history_tree)

        # Connecter les signaux
        self.refresh_btn.clicked.connect(self.load_history)
        self.clear_btn.clicked.connect(self._clear_history)
        self.export_btn.clicked.connect(self._export_history)

    def set_db_manager(self, db_manager):
        """Définir le gestionnaire de base de données"""
        self.db_manager = db_manager
        self.load_history()

    def add_action(self, action_type: str, details: str, result: str):
        """Ajouter une action à l'historique"""
        if not self.db_manager:
            return

        from datetime import datetime
        import getpass

        # Insérer dans la base de données
        query = """
            INSERT INTO cleanup_history (timestamp, action_type, details, result, user)
            VALUES (?, ?, ?, ?, ?)
        """
        values = (
            datetime.now().isoformat(),
            action_type,
            details,
            result,
            getpass.getuser()
        )

        # Créer la table si elle n'existe pas
        self._ensure_history_table()

        result = self.db_manager.execute_insert(query, values)
        success = result is not None
        if success:
            self.load_history()  # Recharger pour afficher la nouvelle entrée

    def _ensure_history_table(self):
        """Créer la table d'historique si elle n'existe pas"""
        create_table_query = """
            CREATE TABLE IF NOT EXISTS cleanup_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                details TEXT,
                result TEXT,
                user TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        self.db_manager.execute_custom_query(create_table_query)

    def load_history(self):
        """Charger l'historique des actions"""
        if not self.db_manager:
            return

        self._ensure_history_table()

        # Requête pour récupérer l'historique
        query = """
            SELECT timestamp, action_type, details, result, user
            FROM cleanup_history
            ORDER BY timestamp DESC
            LIMIT 100
        """

        results = self.db_manager.execute_query(query)
        self.history_actions = results or []

        # Peupler l'arbre
        self.history_tree.clear()

        for row in self.history_actions:
            timestamp = row[0]
            action_type = row[1]
            details = row[2] or ""
            result = row[3] or ""
            user = row[4] or ""

            # Formater la date
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp)
                formatted_date = dt.strftime("%d/%m/%Y %H:%M:%S")
            except:
                formatted_date = timestamp

            item = QTreeWidgetItem([
                formatted_date,
                action_type,
                details,
                result,
                user
            ])

            self.history_tree.addTopLevelItem(item)

        # Ajuster les colonnes
        for i in range(self.history_tree.columnCount()):
            self.history_tree.resizeColumnToContents(i)

        app_logger.info(f"Chargé {len(self.history_actions)} entrées d'historique")

    def _clear_history(self):
        """Vider l'historique après confirmation"""
        reply = QMessageBox.question(
            self,
            "Confirmation de suppression",
            "Êtes-vous sûr de vouloir vider l'historique des actions?\n\n"
            "Cette action est irréversible.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Supprimer de la base de données
        delete_query = "DELETE FROM cleanup_history"
        result = self.db_manager.execute_custom_query(delete_query)
        success = True  # execute_custom_query n'a pas d'erreur si ça marche

        if success:
            self.load_history()
            QMessageBox.information(self, "Historique vidé", "L'historique a été vidé avec succès.")
        else:
            QMessageBox.warning(self, "Erreur", "Erreur lors de la suppression de l'historique.")

    def _export_history(self):
        """Exporter l'historique en CSV"""
        from ..ui.qt_imports import QFileDialog
        import csv
        from datetime import datetime

        if not self.history_actions:
            QMessageBox.warning(self, "Aucune donnée", "Aucun historique à exporter.")
            return

        # Demander le nom du fichier
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter l'historique",
            f"historique_nettoyage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "Fichiers CSV (*.csv)"
        )

        if not filename:
            return

        # Exporter en CSV
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Date/Heure", "Action", "Détails", "Résultat", "Utilisateur"])

            for row in self.history_actions:
                writer.writerow(row)

        QMessageBox.information(self, "Export réussi", f"Historique exporté vers:\n{filename}")