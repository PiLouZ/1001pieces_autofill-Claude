"""
Groupe « ▲ [n incomplètes] ▼ » de la barre d'état, sous le tableau.

- Bouton central : filtre « Lignes à traiter » (compteur et visibilité pilotés
  par IncompleteButtonService).
- Flèches : ligne incomplète précédente/suivante, quelle que soit la colonne
  sélectionnée (logique dans TableController.set_incomplete_nav_buttons),
  masquées avec le bouton quand il n'y a plus de ligne incomplète.
- Raccourcis ⌥⌘↑ / ⌥⌘↓ (Ctrl+Alt+flèche hors macOS).

creer_fleche_nav sert aussi aux flèches « ligne à vérifier » autour de
« Auto-complétés à vérifier » (main_refactored._setup_statusbar).
"""

import qtawesome as qta

from ..utils.qt_imports import QWidget, QHBoxLayout, QPushButton, QToolButton, QAction, QKeySequence, Qt
from .style_manager import StyleManager


class IncompleteNavWidget(QWidget):
    """Conteneur toujours présent : IncompleteButtonService masque/affiche les
    boutons À L'INTÉRIEUR, jamais le conteneur lui-même."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

        layout = QHBoxLayout(self)
        # Marge gauche : le groupe démarre sous le tableau, pas collé au bord
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(2)

        self.prev_btn = self._create_nav_button('up')
        layout.addWidget(self.prev_btn)

        self.filter_btn = QPushButton("Lignes à traiter")
        self.filter_btn.setObjectName("incompleteBtn")
        self.filter_btn.setCheckable(True)
        self.filter_btn.setToolTip("Afficher uniquement les lignes avec des champs vides")
        self.filter_btn.setIcon(qta.icon('fa5s.tasks', color='#555555'))
        # Style (neutre/alerte) appliqué par IncompleteButtonService (StyleManager)
        self.filter_btn.setStyleSheet(StyleManager.HEALTH_BTN_NEUTRAL)
        self.filter_btn.clicked.connect(main_window._toggle_incomplete_filter)
        layout.addWidget(self.filter_btn)

        self.next_btn = self._create_nav_button('down')
        layout.addWidget(self.next_btn)

    def content_height(self) -> int:
        """Hauteur des boutons, même masqués : sert à figer la hauteur de la
        barre d'état pour qu'elle ne change pas quand le groupe apparaît."""
        return max(w.sizeHint().height() for w in (self.prev_btn, self.filter_btn, self.next_btn))

    def _create_nav_button(self, direction: str) -> QToolButton:
        """Flèche ▲/▼ « ligne incomplète » + raccourci ⌥⌘↑ / ⌥⌘↓."""
        up = direction == 'up'
        return creer_fleche_nav(
            self.main_window, direction,
            QKeySequence("Ctrl+Alt+Up" if up else "Ctrl+Alt+Down"),
            "Ligne incomplète précédente" if up else "Ligne incomplète suivante",
            "Type ou Fabricant vide, quelle que soit la colonne sélectionnée",
            'incomplete')


def creer_fleche_nav(main_window, direction: str, sequence: QKeySequence,
                     label: str, detail: str, critere: str) -> QToolButton:
    """Flèche ▲/▼ de la barre d'état + son raccourci.

    Le raccourci est porté par une QAction ajoutée à la fenêtre principale
    (contexte fenêtre) : il fonctionne quel que soit le widget qui a le focus,
    y compris le tableau, qui consomme lui-même les flèches. Il passe par
    TableController.skip_to_row, qui ne fait rien si la flèche est grisée ou
    masquée — clavier et souris se comportent à l'identique.
    """
    up = direction == 'up'
    btn = QToolButton()
    btn.setIcon(qta.icon('fa5s.chevron-up' if up else 'fa5s.chevron-down',
                         color='#555555', color_disabled='#c4c8cc'))
    btn.setStyleSheet(StyleManager.HEALTH_NAV_BTN)
    btn.setEnabled(False)  # activée par TableController selon le périmètre affiché
    btn.setToolTip(f"{label} ({sequence.toString(QKeySequence.NativeText)})\n{detail}")

    shortcut_action = QAction(label, main_window)
    shortcut_action.setShortcut(sequence)
    shortcut_action.setShortcutContext(Qt.WindowShortcut)
    shortcut_action.triggered.connect(
        lambda: main_window.table_controller.skip_to_row(critere, direction)
        if getattr(main_window, 'table_controller', None) else None
    )
    main_window.addAction(shortcut_action)
    return btn
