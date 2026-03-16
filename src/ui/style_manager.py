"""
Style Manager - Phase 2 Refactoring
Gestion centralisée des styles et thèmes de l'application
"""

class StyleManager:
    """Gestionnaire centralisé des styles CSS modernes"""
    
    @staticmethod
    def get_modern_style() -> str:
        """Retourner le style CSS moderne complet de l'application"""
        return """
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

        /* === COMBOBOX SPECIFIQUE === */
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        
        QComboBox::down-arrow {
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid #6c757d;
            margin-right: 8px;
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
        QToolTip {
            background-color: #ffffff;
            color: #2c3e50;
            border: 1px solid #ced4da;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
            font-family: -apple-system, 'SF Pro Display', system-ui, 'Helvetica Neue', sans-serif;
        }

        /* === ANIMATIONS SUBTILES === */
        /* Transitions not supported in PyQt5 */

        /* Transitions not supported in PyQt5 - removed */
        """