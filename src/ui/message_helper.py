"""
🗨️ MessageHelper - Gestionnaire centralisé des messages utilisateur
Élimine la duplication des 39 occurrences de QMessageBox dans le projet
"""

from typing import Optional, Union
from .qt_imports import QMessageBox, QWidget


class MessageType:
    """Types de messages standardisés"""
    INFO = "Information"
    WARNING = "Attention"
    ERROR = "Erreur"
    SUCCESS = "Succès"
    QUESTION = "Question"


class MessageHelper:
    """
    Helper centralisé pour tous les messages utilisateur
    Remplace les multiples QMessageBox.* dispersés dans le code
    """
    
    @staticmethod
    def show_info(parent: Optional[QWidget], message: str, title: str = MessageType.INFO) -> None:
        """Afficher un message d'information"""
        QMessageBox.information(parent, title, message)
    
    @staticmethod
    def show_success(parent: Optional[QWidget], message: str, title: str = MessageType.SUCCESS) -> None:
        """Afficher un message de succès"""
        QMessageBox.information(parent, title, message)
    
    @staticmethod
    def show_warning(parent: Optional[QWidget], message: str, title: str = MessageType.WARNING) -> None:
        """Afficher un message d'avertissement"""
        QMessageBox.warning(parent, title, message)
    
    @staticmethod
    def show_error(parent: Optional[QWidget], message: str, title: str = MessageType.ERROR) -> None:
        """Afficher un message d'erreur"""
        QMessageBox.critical(parent, title, message)
    
    @staticmethod
    def ask_question(parent: Optional[QWidget], message: str, title: str = MessageType.QUESTION) -> bool:
        """
        Poser une question oui/non
        Returns: True si l'utilisateur clique sur Yes/Oui
        """
        reply = QMessageBox.question(
            parent, title, message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes
    
    @staticmethod
    def ask_question_with_cancel(
        parent: Optional[QWidget], 
        message: str, 
        title: str = MessageType.QUESTION
    ) -> Optional[bool]:
        """
        Poser une question oui/non/annuler
        Returns: True (Oui), False (Non), None (Annuler)
        """
        reply = QMessageBox.question(
            parent, title, message,
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        
        if reply == QMessageBox.Yes:
            return True
        elif reply == QMessageBox.No:
            return False
        else:  # Cancel
            return None
    
    @staticmethod
    def show_detailed_error(
        parent: Optional[QWidget], 
        message: str, 
        details: str, 
        title: str = MessageType.ERROR
    ) -> None:
        """Afficher une erreur avec détails techniques"""
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setDetailedText(details)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.exec_()
    
    @staticmethod
    def show_custom(
        parent: Optional[QWidget],
        title: str,
        message: str,
        icon: QMessageBox.Icon = QMessageBox.Information,
        buttons: QMessageBox.StandardButtons = QMessageBox.Ok
    ) -> int:
        """Afficher un message personnalisé"""
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(icon)
        msg_box.setStandardButtons(buttons)
        return msg_box.exec_()


class CommonMessages:
    """Messages couramment utilisés dans l'application"""
    
    # Messages de succès
    SAVE_SUCCESS = "Les données ont été sauvegardées avec succès."
    EXPORT_SUCCESS = "L'export a été généré avec succès."
    IMPORT_SUCCESS = "L'import a été effectué avec succès."
    DELETE_SUCCESS = "L'élément a été supprimé avec succès."
    
    # Messages d'erreur
    SAVE_ERROR = "Erreur lors de la sauvegarde des données."
    EXPORT_ERROR = "Erreur lors de l'export des données."
    IMPORT_ERROR = "Erreur lors de l'import des données."
    DELETE_ERROR = "Erreur lors de la suppression."
    DATABASE_ERROR = "Erreur de base de données."
    FILE_NOT_FOUND = "Fichier non trouvé."
    PERMISSION_ERROR = "Permissions insuffisantes."
    
    # Messages de confirmation
    CONFIRM_DELETE = "Êtes-vous sûr de vouloir supprimer cet élément ?"
    CONFIRM_OVERWRITE = "Le fichier existe déjà. Voulez-vous le remplacer ?"
    CONFIRM_EXIT = "Voulez-vous vraiment quitter l'application ?"
    
    # Messages d'information
    NO_DATA_SELECTED = "Aucune donnée sélectionnée."
    OPERATION_CANCELLED = "Opération annulée par l'utilisateur."
    PROCESSING = "Traitement en cours..."


# Fonctions de commodité pour l'usage courant
def show_success(parent: Optional[QWidget], message: str = CommonMessages.SAVE_SUCCESS) -> None:
    """Raccourci pour afficher un message de succès"""
    MessageHelper.show_success(parent, message)


def show_error(parent: Optional[QWidget], message: str, details: str = None) -> None:
    """Raccourci pour afficher une erreur (avec détails optionnels)"""
    if details:
        MessageHelper.show_detailed_error(parent, message, details)
    else:
        MessageHelper.show_error(parent, message)


def ask_confirmation(parent: Optional[QWidget], message: str = CommonMessages.CONFIRM_DELETE) -> bool:
    """Raccourci pour demander une confirmation"""
    return MessageHelper.ask_question(parent, message)