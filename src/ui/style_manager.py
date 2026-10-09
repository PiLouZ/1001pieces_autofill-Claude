"""
Style Manager - Phase 2 Refactoring
Gestion centralisée des styles et thèmes de l'application
"""

import os
import tempfile

_combo_arrow_path: str = ""


def _generate_combo_arrow() -> str:
    """Génère une icône chevron-down via qtawesome, la sauve en PNG et retourne son chemin."""
    global _combo_arrow_path
    if _combo_arrow_path:
        return _combo_arrow_path
    try:
        import qtawesome as qta
        icon = qta.icon('fa5s.chevron-down', color='#6c757d')
        pixmap = icon.pixmap(10, 10)
        path = os.path.join(tempfile.gettempdir(), '1001pieces_combo_arrow.png')
        pixmap.save(path)
        _combo_arrow_path = path
    except Exception:
        _combo_arrow_path = ""
    return _combo_arrow_path


_inline_icon_paths: dict = {}


def inline_icon_html(icon_name: str, color: str, size: int = 11) -> str:
    """Icône qtawesome insérable dans le texte riche d'un QLabel (`<img>`).

    Remplace les glyphes (⚠, ✓…) dans les libellés : l'icône est rendue en PNG
    une seule fois par (nom, couleur, taille), comme le chevron des listes
    déroulantes. Chaîne vide si qtawesome échoue (le texte reste lisible).
    """
    key = (icon_name, color, size)
    path = _inline_icon_paths.get(key)
    if path is None:
        try:
            import qtawesome as qta
            pixmap = qta.icon(icon_name, color=color).pixmap(size * 2, size * 2)
            safe = f"{icon_name}_{color}_{size}".replace('.', '_').replace('#', '')
            path = os.path.join(tempfile.gettempdir(), f'1001pieces_icone_{safe}.png')
            pixmap.save(path)
        except Exception:
            path = ""
        _inline_icon_paths[key] = path
    if not path:
        return ""
    # Image 2× affichée à `size` : nette sur écran Retina
    return f'<img src="{path}" width="{size}" height="{size}" style="vertical-align: middle;">'


class StyleManager:
    """Gestionnaire centralisé des styles CSS modernes

    Palette de référence : `Config.Colors` (src/core/config.py) — PRIMARY #0d6efd,
    SUCCESS #198754, DANGER #dc3545, WARNING #fd7e14 et leurs variantes survol /
    fond / texte. Toute nouvelle couleur de rôle (bouton principal, validation,
    erreur, focus) doit en reprendre la valeur. Les couleurs de CATÉGORIE (types
    d'action de l'historique, relations Remplace / Remplacée par / Équivalence)
    sont volontairement distinctes et ne s'y rattachent pas.
    """

    # === Styles QSS réutilisables (boutons plats / transparents) ===
    # Centralisés ici pour éviter la duplication de ces littéraux dans les
    # multiples fenêtres (cf. audit structure 2026-06-11, point 9).

    # Style nu pour un widget plat sans bord ni fond (ex: bouton-spinner)
    FLAT_TRANSPARENT = "border: none; background: transparent;"

    # Idem mais ciblé sur QPushButton
    FLAT_TRANSPARENT_BUTTON = "QPushButton { border: none; background: transparent; }"

    # Bouton-icône compact sans marge ni contour (ex: icônes d'action inline)
    ICON_BUTTON = (
        "QPushButton { border: none; background: transparent; "
        "padding: 0; margin: 0; outline: none; }"
    )

    # Bouton de rafraîchissement plat avec survol discret
    REFRESH_BUTTON = (
        "QPushButton { border: none; background: transparent; } "
        "QPushButton:hover { background: rgba(0,0,0,0.08); border-radius: 3px; }"
    )

    # === Cluster "santé des données" — boutons toolbar (lignes incomplètes / doublons) ===
    # Géométrie UNIQUE et partagée par les deux boutons (cf. IncompleteButtonService et
    # DuplicateIndicatorService) : même padding/bordure/rayon/police → les deux boutons
    # restent rigoureusement de même taille par construction ; seule la couleur change
    # selon l'état (neutre au repos, orange en alerte). Toute modif de ces styles se fait
    # ICI uniquement, jamais en dupliquant le littéral dans les services.
    HEALTH_BTN_NEUTRAL = (
        "QPushButton { background-color: #f8f9fa; color: #495057;"
        " border: 2px solid #ced4da; border-radius: 4px; padding: 3px 9px; font-size: 11px; }"
        "QPushButton:hover { background-color: #e9ecef; }"
    )
    HEALTH_BTN_ALERT = (
        "QPushButton {"
        " background-color: #ff6b35; color: white; font-weight: bold;"
        " border: 2px solid #e55a2b; border-radius: 4px; padding: 3px 9px; font-size: 11px; }"
        "QPushButton:hover { background-color: #e55a2b; }"
    )

    # Flèches ▲/▼ qui encadrent « Lignes à traiter » : même bordure 2px et même
    # rayon que les boutons du cluster → même hauteur, alignées sans retouche.
    HEALTH_NAV_BTN = (
        "QToolButton { background-color: #f8f9fa; border: 2px solid #ced4da;"
        " border-radius: 4px; padding: 3px 4px; }"
        "QToolButton:hover { background-color: #e9ecef; }"
        "QToolButton:disabled { background-color: #f8f9fa; border-color: #e9ecef; }"
    )

    # === Boutons d'export (fenêtre principale) — état inactif commun ===
    # Chaque bouton garde sa couleur active propre (CSV sarcelle, Méta Title orange,
    # Méta Desc jaune, HTML blancs) ; seul l'état inactif est partagé, pour qu'on
    # distingue d'un coup d'œil ce qui est cliquable. Avant : les HTML inactifs
    # ressemblaient à leur état actif, et CSV/Méta inactifs étaient gris foncé.
    # Pas de propriété `border` ici : chaque bouton garde l'épaisseur de bordure de
    # son état actif (aucune pour CSV/Méta, 1 px pour HTML), sinon le bouton
    # changerait de taille en s'activant.
    EXPORT_BTN_DISABLED_RULES = "background: #f1f3f5; color: #adb5bd;"

    # Bouton « effacer les filtres » (icône ✕ qtawesome) : gris neutre au repos
    # (vider des champs n'est pas une action destructrice), rouge pâle au survol.
    CLEAR_FILTERS_BUTTON = (
        "QPushButton { background-color: #f8f9fa; color: #868e96;"
        " border: 1px solid #ced4da; border-radius: 3px;"
        " padding: 0px; }"
        "QPushButton:hover { background-color: #f8d7da; border-color: #f1aeb5; }"
        "QPushButton:pressed { background-color: #f1aeb5; border-color: #ea868f; }"
    )

    # Petits boutons-icônes plats (en-tête du panneau des pièces) : sans cadre,
    # fond discret au survol — même famille que le bouton d'ouverture de l'historique.
    PANEL_ICON_BUTTON = (
        "QPushButton { background: transparent; border: none; border-radius: 3px;"
        " min-width: 22px; max-width: 22px; min-height: 20px; max-height: 20px; padding: 0px; }"
        "QPushButton:hover { background-color: #e9ecef; }"
    )

    # Carte « nouvelle pièce » du panneau des pièces (PieceAddCard) : contour
    # pointillé bleu = élément en cours de création ; champs et boutons compacts
    # (le style global des champs, 8 px de marge, est trop haut pour ce panneau).
    PIECE_ADD_CARD = (
        "QFrame#pieceAddCard { background: white; border: 1px dashed #80bdff; border-radius: 6px; }"
        "QFrame#pieceAddCard QLineEdit { padding: 3px 8px; border: 1px solid #ced4da;"
        " border-radius: 4px; font-size: 12px; background: white; }"
        "QFrame#pieceAddCard QLineEdit:focus { border-color: #80bdff; }"
        "QLineEdit#pieceAddRef { font-weight: bold; }"
        "QLabel#pieceAddTarget { background: #e7f1ff; color: #0b5ed7; border-radius: 3px;"
        " padding: 1px 6px; font-size: 11px; }"
        "QLabel#pieceAddHint { color: #adb5bd; font-size: 11px; }"
        "QPushButton#pieceAddCancel { background: transparent; border: none; color: #6c757d;"
        " padding: 3px 8px; font-size: 12px; font-weight: normal; min-height: 0px; }"
        "QPushButton#pieceAddCancel:hover { color: #212529; background: #e9ecef; border-radius: 4px; }"
        "QPushButton#pieceAddSubmit { background: #0d6efd; color: white; border: none;"
        " border-radius: 4px; padding: 3px 12px; font-size: 12px; font-weight: 600; min-height: 0px; }"
        "QPushButton#pieceAddSubmit:hover { background: #0b5ed7; }"
        "QPushButton#pieceAddSubmit:pressed { background: #0a58ca; }"
    )

    # Barre de filtres compacte des fenêtres secondaires : liste déroulante, champs
    # texte et dates à la même hauteur (le style global des champs, 8 px de marge,
    # rendait la liste déroulante deux fois plus haute que les champs de date).
    COMPACT_FILTER_BAR = (
        "QComboBox, QLineEdit, QDateEdit { padding: 3px 8px; min-height: 20px;"
        " border: 1px solid #ced4da; border-radius: 4px; background: white; }"
        "QComboBox:focus, QLineEdit:focus, QDateEdit:focus { border-color: #80bdff; }"
    )

    # Surlignage temporaire d'une pièce tout juste ajoutée (vert pâle, 2 s)
    PIECE_ADDED_HIGHLIGHT = "#d1e7dd"

    @staticmethod
    def get_modern_style() -> str:
        """Retourner le style CSS moderne complet de l'application"""
        arrow_path = _generate_combo_arrow()
        arrow_rule = (
            f"image: url({arrow_path}); width: 10px; height: 10px; margin-right: 4px;"
            if arrow_path else
            "width: 8px; height: 8px; margin-right: 4px;"
        )
        style = """
        /* === RESET ET BASE === */
        QWidget {
            font-family: -apple-system, 'SF Pro Display', system-ui, 'Helvetica Neue', sans-serif;
            font-size: 13px;
        }

        /* === WINDOW PRINCIPALE === */
        QMainWindow {
            background-color: #f8f9fa;
            color: #212529;
        }

        /* === BOUTONS MODERNES === */
        QPushButton {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #ffffff, stop: 1 #f8f9fa);
            border: 1px solid #dee2e6;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 500;
            color: #495057;
            min-height: 16px;
        }
        
        QPushButton:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #e9ecef, stop: 1 #dee2e6);
            border-color: #adb5bd;
            color: #212529;
        }
        
        QPushButton:pressed {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #dee2e6, stop: 1 #ced4da);
            border-color: #6c757d;
        }
        
        QPushButton:disabled {
            background-color: #f8f9fa;
            color: #6c757d;
            border-color: #e9ecef;
        }

        /* === BOUTONS PRIMAIRES === */
        QPushButton[class="primary"] {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #0d6efd, stop: 1 #0b5ed7);
            border: 1px solid #0a58ca;
            color: white;
            font-weight: 600;
        }
        
        QPushButton[class="primary"]:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #0b5ed7, stop: 1 #0a58ca);
            border-color: #0a53be;
        }
        
        QPushButton[class="primary"]:pressed {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #0a58ca, stop: 1 #0a53be);
        }

        /* === BOUTONS SUCCESS === */
        QPushButton[class="success"] {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #198754, stop: 1 #157347);
            border: 1px solid #146c43;
            color: white;
            font-weight: 600;
        }
        
        QPushButton[class="success"]:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #157347, stop: 1 #146c43);
            border-color: #13653f;
        }

        /* === BOUTONS WARNING === */
        QPushButton[class="warning"] {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #fd7e14, stop: 1 #e8680d);
            border: 1px solid #d96c0c;
            color: white;
            font-weight: 600;
        }
        
        QPushButton[class="warning"]:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #e8680d, stop: 1 #d96c0c);
            border-color: #ca650b;
        }

        /* === BOUTONS DANGER === */
        QPushButton[class="danger"] {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #dc3545, stop: 1 #c82333);
            border: 1px solid #bd2130;
            color: white;
            font-weight: 600;
        }
        
        QPushButton[class="danger"]:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #c82333, stop: 1 #bd2130);
            border-color: #b21e2d;
        }

        /* === CHAMPS DE SAISIE === */
        QLineEdit, QTextEdit, QComboBox {
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 8px 12px;
            background-color: white;
            color: #495057;
            selection-background-color: #0d6efd;
        }
        
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
            border-color: #80bdff;
            outline: 0;
        }
        
        QLineEdit:hover, QTextEdit:hover, QComboBox:hover {
            border-color: #adb5bd;
        }

        /* Éditeur de cellule des tableaux (double-clic / F2) : sans la marge
           intérieure de 8 px des champs de formulaire, qui ne laissait que 7 px au
           texte dans une ligne de 26 px. Bordure bleue = cellule en édition. */
        QTableView QLineEdit {
            padding: 0px 4px;
            border: 1px solid #80bdff;
            border-radius: 0px;
        }

        /* === COMBOBOX SPECIFIQUE === */
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        
        QComboBox::down-arrow {
            %%ARROW_RULE%%
        }

        /* Champs de date à calendrier : même chevron que les listes déroulantes
           (sinon bloc sombre natif) */
        QDateEdit::drop-down {
            border: none;
            width: 20px;
        }

        QDateEdit::down-arrow {
            %%ARROW_RULE%%
        }
        
        QComboBox QAbstractItemView {
            border: 1px solid #ced4da;
            background-color: white;
            selection-background-color: #e7f1ff;
            selection-color: #0d6efd;
            outline: none;
        }

        /* === TABLEAUX === */
        QTableWidget {
            background-color: white;
            alternate-background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            gridline-color: #e9ecef;
            selection-background-color: #0056b3;
            selection-color: white;
        }
        
        /* Tableau principal (QTableView, non couvert par la règle QTableWidget) :
           une ligne sur deux teintée — le gris par défaut de Qt (#f7f7f7) était
           à peine visible sur fond blanc. */
        CustomTableView {
            alternate-background-color: #f1f4f8;
        }

        QHeaderView::section {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #f8f9fa, stop: 1 #e9ecef);
            border: 1px solid #dee2e6;
            border-left: none;
            padding: 8px 12px;
            font-weight: 600;
            color: #495057;
        }
        
        QHeaderView::section:first {
            border-left: 1px solid #dee2e6;
        }

        /* Numéros de ligne : pas de marge verticale, sinon ils seraient rognés
           avec les hauteurs de ligne réduites (réglage Affichage → Hauteur). */
        QHeaderView::section:vertical {
            padding: 0px 8px;
        }
        
        QHeaderView::section:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #e9ecef, stop: 1 #dee2e6);
        }

        /* === ONGLETS === */
        QTabWidget::pane {
            border: 1px solid #dee2e6;
            background-color: white;
            border-radius: 0 6px 6px 6px;
        }
        
        QTabBar::tab {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #f8f9fa, stop: 1 #e9ecef);
            border: 1px solid #dee2e6;
            border-bottom: none;
            padding: 8px 16px;
            margin-right: 2px;
            color: #6c757d;
            border-radius: 6px 6px 0 0;
        }
        
        QTabBar::tab:selected {
            background: white;
            color: #0d6efd;
            font-weight: 600;
            border-bottom: 1px solid white;
        }
        
        QTabBar::tab:hover:!selected {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #e9ecef, stop: 1 #dee2e6);
            color: #495057;
        }

        /* === LISTES === */
        QListWidget {
            background-color: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            outline: none;
        }
        
        QListWidget::item {
            padding: 8px 12px;
            border-bottom: 1px solid #f8f9fa;
        }
        
        QListWidget::item:selected {
            background-color: #e7f1ff;
            color: #0d6efd;
        }
        
        QListWidget::item:hover {
            background-color: #f8f9fa;
        }

        /* === BARRES DE DÉFILEMENT === */
        QScrollBar:vertical {
            border: none;
            background-color: #f8f9fa;
            width: 12px;
            border-radius: 6px;
        }
        
        QScrollBar::handle:vertical {
            background-color: #ced4da;
            border-radius: 6px;
            min-height: 20px;
        }
        
        QScrollBar::handle:vertical:hover {
            background-color: #adb5bd;
        }
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        
        QScrollBar:horizontal {
            border: none;
            background-color: #f8f9fa;
            height: 12px;
            border-radius: 6px;
        }
        
        QScrollBar::handle:horizontal {
            background-color: #ced4da;
            border-radius: 6px;
            min-width: 20px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background-color: #adb5bd;
        }
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0;
        }

        /* === BARRE DE STATUT === */
        QStatusBar {
            background-color: #e9ecef;
            border-top: 1px solid #dee2e6;
            color: #495057;
            font-size: 12px;
        }

        /* === TOOLBAR === */
        QToolBar {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #ffffff, stop: 1 #f8f9fa);
            border: none;
            border-bottom: 1px solid #dee2e6;
            spacing: 4px;
            padding: 4px;
        }
        
        QToolBar::separator {
            background-color: #dee2e6;
            width: 1px;
            margin: 4px 8px;
        }

        /* Actions et menus déroulants de la barre d'outils : un seul style plat
           (texte sans cadre, fond discret au survol). Les menus Affichage /
           Données / Configuration ne se distinguent plus que par leur chevron. */
        QToolBar QToolButton {
            background: transparent;
            border: none;
            border-radius: 4px;
            padding: 4px 6px;
            color: #212529;
        }

        QToolBar QToolButton:hover {
            background-color: #e9ecef;
        }

        QToolBar QToolButton:pressed {
            background-color: #dee2e6;
        }

        QToolBar QToolButton:disabled {
            color: #adb5bd;
        }

        QPushButton#menuButton {
            background: transparent;
            border: none;
            border-radius: 4px;
            padding: 4px 22px 4px 6px;
            font-weight: normal;
            color: #212529;
            min-height: 0px;
        }

        QPushButton#menuButton:hover {
            background-color: #e9ecef;
        }

        QPushButton#menuButton:pressed {
            background-color: #dee2e6;
        }

        QPushButton#menuButton::menu-indicator {
            %%MENU_ARROW_RULE%%
            subcontrol-origin: padding;
            subcontrol-position: right center;
            right: 6px;
        }

        /* === PROGRESS BAR === */
        QProgressBar {
            border: 1px solid #dee2e6;
            border-radius: 6px;
            background-color: #f8f9fa;
            text-align: center;
            color: #495057;
            font-weight: 600;
        }
        
        QProgressBar::chunk {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #0d6efd, stop: 1 #0b5ed7);
            border-radius: 6px;
        }

        /* === CHECKBOXES === */
        QCheckBox {
            spacing: 8px;
            color: #495057;
        }
        
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border: 2px solid #ced4da;
            border-radius: 3px;
            background-color: white;
        }
        
        QCheckBox::indicator:hover {
            border-color: #adb5bd;
        }
        
        QCheckBox::indicator:checked {
            background-color: #0d6efd;
            border-color: #0d6efd;
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xMC42IDEuNEw0LjIgNy44TDEuNCAwIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgo8L3N2Zz4K);
        }

        /* === DIALOG BOXES === */
        QDialog {
            background-color: #ffffff;
            border: 1px solid #dee2e6;
            border-radius: 8px;
        }

        /* === SPLITTER === */
        QSplitter::handle {
            background-color: #dee2e6;
        }
        
        QSplitter::handle:vertical {
            height: 2px;
        }
        
        QSplitter::handle:horizontal {
            width: 2px;
        }
        
        QSplitter::handle:hover {
            background-color: #0d6efd;
        }

        /* === GROUPBOX === */
        QGroupBox {
            font-weight: 600;
            color: #495057;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            margin-top: 1ex;
            padding-top: 16px;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 8px 0 8px;
            background-color: #f8f9fa;
        }

        /* === MENU BAR === */
        QMenuBar {
            background-color: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
            color: #495057;
        }
        
        QMenuBar::item {
            padding: 8px 16px;
            background: transparent;
        }
        
        QMenuBar::item:selected {
            background-color: #e9ecef;
            color: #212529;
        }

        /* === CONTEXT MENU === */
        QMenu {
            background-color: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            padding: 4px 0;
            color: #495057;
        }
        
        QMenu::item {
            padding: 8px 16px;
            background: transparent;
        }
        
        QMenu::item:selected {
            background-color: #e7f1ff;
            color: #0d6efd;
        }
        
        QMenu::separator {
            height: 1px;
            background-color: #e9ecef;
            margin: 4px 0;
        }

        /* === NOTIFICATIONS INLINE === */
        QLabel[class="alert-success"] {
            background-color: #d1e7dd;
            color: #0a3622;
            border: 1px solid #b3d3c4;
            border-radius: 6px;
            padding: 8px 12px;
        }
        
        QLabel[class="alert-warning"] {
            background-color: #fff3cd;
            color: #664d03;
            border: 1px solid #f1c40f;
            border-radius: 6px;
            padding: 8px 12px;
        }
        
        QLabel[class="alert-danger"] {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f1c2c7;
            border-radius: 6px;
            padding: 8px 12px;
        }

        /* === TOOLTIPS === */
        /* Infobulles sombres et compactes (esprit macOS natif) : se détachent
           des fenêtres blanches sans cadre.
           Piège mesuré : sur une infobulle, Qt convertit `padding` en UNE marge
           identique sur les 4 côtés (2 px + la plus grande valeur) — « 3px 7px »
           donnait 9 px partout. D'où une valeur unique et petite : 41 px de haut
           pour 2 lignes, contre ~59 px avant. */
        QToolTip {
            background-color: #343a40;
            color: #f8f9fa;
            border: 1px solid #343a40;
            border-radius: 4px;
            padding: 2px;
            font-size: 11px;
            font-family: -apple-system, 'SF Pro Display', system-ui, 'Helvetica Neue', sans-serif;
        }

        /* === ANIMATIONS SUBTILES === */
        /* Transitions not supported in PyQt5 */

        /* Transitions not supported in PyQt5 - removed */
        """
        menu_arrow_rule = (
            f"image: url({arrow_path}); width: 10px; height: 10px;"
            if arrow_path else
            "width: 8px; height: 8px;"
        )
        return (style.replace('%%ARROW_RULE%%', arrow_rule)
                     .replace('%%MENU_ARROW_RULE%%', menu_arrow_rule))