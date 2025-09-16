"""
Dialog de progression pour lecture asynchrone des fichiers
Interface non-bloquante avec possibilité d'annulation
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                           QPushButton, QProgressBar, QTextEdit)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont


class FileReadingProgressDialog(QDialog):
    """
    Dialog de progression pour la lecture asynchrone des fichiers
    Préserve l'interactivité de l'interface utilisateur
    """
    
    # Signal émis quand l'utilisateur annule
    cancelled = pyqtSignal()
    
    def __init__(self, parent=None, title="Lecture des fichiers..."):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)  # IMPORTANT: Non-modal pour préserver l'UI
        self.setFixedSize(500, 300)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        
        self._setup_ui()
        self._is_cancelled = False
        
    def _setup_ui(self):
        """Initialiser l'interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Titre principal
        title_label = QLabel("Lecture des fichiers en cours...")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Label de status
        self.status_label = QLabel("Préparation...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Zone de détails (optionnelle)
        self.details_text = QTextEdit()
        self.details_text.setMaximumHeight(100)
        self.details_text.setVisible(False)  # Caché par défaut
        layout.addWidget(self.details_text)
        
        # Boutons
        button_layout = QHBoxLayout()
        
        self.details_button = QPushButton("Afficher détails")
        self.details_button.clicked.connect(self._toggle_details)
        button_layout.addWidget(self.details_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.clicked.connect(self._cancel_reading)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
    def update_progress(self, current: int, total: int, filename: str = ""):
        """
        Mettre à jour la progression
        
        Args:
            current: Fichier actuel (1-based)
            total: Total de fichiers
            filename: Nom du fichier en cours
        """
        if self._is_cancelled:
            return
            
        # Calcul pourcentage
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)
        
        # Status
        status_text = f"Fichier {current}/{total}"
        if filename:
            status_text += f": {filename}"
        self.status_label.setText(status_text)
        
        # Détails
        if filename:
            self.details_text.append(f"[{current}/{total}] {filename}")
        
        # Forcer mise à jour UI
        self.repaint()
        
    def add_detail(self, message: str):
        """Ajouter un message de détail"""
        self.details_text.append(message)
        
    def set_completed(self, success_count: int, total_count: int):
        """Marquer comme terminé"""
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Terminé: {success_count}/{total_count} fichiers lus")
        self.cancel_button.setText("Fermer")
        
    def set_error(self, error_message: str):
        """Afficher une erreur"""
        self.status_label.setText(f"Erreur: {error_message}")
        self.cancel_button.setText("Fermer")
        self.add_detail(f"ERREUR: {error_message}")
        
    def _toggle_details(self):
        """Afficher/masquer les détails"""
        visible = not self.details_text.isVisible()
        self.details_text.setVisible(visible)
        self.details_button.setText("Masquer détails" if visible else "Afficher détails")
        
        # Ajuster taille
        if visible:
            self.setFixedSize(500, 400)
        else:
            self.setFixedSize(500, 300)
            
    def _cancel_reading(self):
        """Annuler la lecture"""
        if not self._is_cancelled:
            self._is_cancelled = True
            self.cancelled.emit()
            self.status_label.setText("Annulation en cours...")
            self.cancel_button.setEnabled(False)
        else:
            self.accept()  # Fermer le dialog
    
    def closeEvent(self, event):
        """Gérer la fermeture du dialog"""
        if not self._is_cancelled:
            self._cancel_reading()
        event.accept()


class ProgressDialogManager:
    """
    Gestionnaire centralisé pour les dialogs de progression
    Intégration propre avec l'ImportManager
    """
    
    def __init__(self, parent_widget=None):
        self.parent_widget = parent_widget
        self.current_dialog = None
        
    def show_file_reading_progress(self, file_count: int, title: str = None) -> FileReadingProgressDialog:
        """
        Afficher un dialog de progression pour lecture de fichiers
        
        Args:
            file_count: Nombre de fichiers à lire
            title: Titre personnalisé
            
        Returns:
            Dialog de progression configuré
        """
        # Fermer dialog existant si ouvert
        if self.current_dialog:
            self.current_dialog.close()
        
        # Titre adaptatif
        if not title:
            if file_count == 1:
                title = "Lecture du fichier..."
            else:
                title = f"Lecture de {file_count} fichiers..."
        
        # Créer et configurer
        self.current_dialog = FileReadingProgressDialog(self.parent_widget, title)
        self.current_dialog.show()
        
        return self.current_dialog
    
    def close_current_dialog(self):
        """Fermer le dialog actuel"""
        if self.current_dialog:
            self.current_dialog.close()
            self.current_dialog = None
            
    def is_dialog_open(self) -> bool:
        """Vérifier si un dialog est ouvert"""
        return self.current_dialog is not None and self.current_dialog.isVisible()