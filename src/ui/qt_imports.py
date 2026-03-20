"""
🎯 Module centralisé des imports PyQt5
Élimine la duplication des imports dans 29 fichiers du projet
"""

# Widgets principaux
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QTextBrowser,
    QTableWidget, QTableWidgetItem, QTableWidgetSelectionRange, QHeaderView,
    QAbstractItemView, QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QComboBox, QCheckBox,
    QInputDialog, QMessageBox, QFileDialog, QProgressDialog, QDialogButtonBox,
    QToolBar, QToolButton, QAction, QStatusBar, QSplitter, QTabWidget,
    QMenu, QMenuBar, QCompleter, QFrame, QScrollArea,
    QGroupBox, QButtonGroup, QRadioButton, QSpinBox,
    QDoubleSpinBox, QSlider, QProgressBar, QDateEdit,
    QTimeEdit, QDateTimeEdit, QCalendarWidget, QSizePolicy,
    QStackedWidget
)

# Core Qt
from PyQt5.QtCore import (
    Qt, QTimer, QSettings, QEvent, QSize, QRect, QPoint,
    QMimeData, QUrl, QThread, QRunnable, QThreadPool,
    QObject, pyqtSignal, pyqtSlot, QVariant, QModelIndex,
    QAbstractTableModel, QSortFilterProxyModel, QStringListModel, QByteArray,
    QIODevice, QTextStream, QFile, QDir, QFileInfo,
    QStandardPaths, QCoreApplication, QPropertyAnimation,
    QEasingCurve, QParallelAnimationGroup
)

# GUI et graphiques
from PyQt5.QtGui import (
    QKeySequence, QPainter, QPen, QColor, QBrush, QKeyEvent,
    QFont, QPixmap, QIcon, QImage, QPalette, QCursor,
    QValidator, QIntValidator, QDoubleValidator, QRegExpValidator,
    QTextCursor, QTextDocument, QTextCharFormat, QSyntaxHighlighter,
    QClipboard, QDrag, QDropEvent, QDragEnterEvent, QDragMoveEvent
)

# Types d'événements Qt couramment utilisés
from PyQt5.QtCore import QEvent as QtEvent

# Alias pour compatibilité avec le code existant
QEventType = QtEvent.Type

__all__ = [
    # Widgets
    'QApplication', 'QMainWindow', 'QWidget', 'QDialog',
    'QVBoxLayout', 'QHBoxLayout', 'QGridLayout', 'QFormLayout',
    'QLabel', 'QPushButton', 'QLineEdit', 'QTextEdit', 'QTextBrowser',
    'QTableWidget', 'QTableWidgetItem', 'QTableWidgetSelectionRange', 'QHeaderView',
    'QAbstractItemView', 'QListWidget', 'QListWidgetItem', 'QTreeWidget', 'QTreeWidgetItem', 'QComboBox', 'QCheckBox',
    'QInputDialog', 'QMessageBox', 'QFileDialog', 'QProgressDialog', 'QDialogButtonBox',
    'QToolBar', 'QToolButton', 'QAction', 'QStatusBar', 'QSplitter', 'QTabWidget',
    'QMenu', 'QMenuBar', 'QCompleter', 'QFrame', 'QScrollArea', 'QSizePolicy', 'QStackedWidget',
    
    # Core
    'Qt', 'QTimer', 'QSettings', 'QEvent', 'QSize', 'QRect', 'QPoint',
    'QMimeData', 'QUrl', 'QThread', 'QRunnable', 'QThreadPool',
    'QObject', 'pyqtSignal', 'pyqtSlot', 'QVariant',
    
    # GUI
    'QKeySequence', 'QPainter', 'QPen', 'QColor', 'QBrush', 'QKeyEvent',
    'QFont', 'QPixmap', 'QIcon', 'QImage', 'QPalette', 'QCursor',
    
    # Aliases
    'QtEvent', 'QEventType'
]