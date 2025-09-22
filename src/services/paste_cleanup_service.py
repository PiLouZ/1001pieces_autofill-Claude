"""
Service de nettoyage automatique du collage dans les champs de recherche
Détecte et nettoie automatiquement les extensions de fichiers (.pdf, .csv, etc.)
"""

import re
from typing import Dict, List, Optional, Tuple
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from ..core.logger import app_logger

class PasteCleanupService(QObject):
    """Service de nettoyage intelligent du contenu collé dans les champs de recherche"""
    
    # Signal émis quand le texte est nettoyé
    text_cleaned = pyqtSignal(str, str)  # (texte_original, texte_nettoyé)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Configuration par défaut
        self._default_extensions = ['.pdf', '.csv', '.xls', '.xlsx', '.doc', '.docx', '.txt', '.json']
        self._user_extensions = self._default_extensions.copy()
        
        # Paramètres utilisateur
        self._default_replacement = '||'  # OU par défaut
        self._ask_confirmation = True  # Demander confirmation à l'utilisateur
        self._remember_choice = True
        self._user_choice_memory = {}  # Cache des choix utilisateur
        
        # Configuration des remplacements
        self._replacement_options = {
            'or': '||',
            'and': '&&',
            'space': ' ',
            'remove': ''
        }
        
    def process_paste_content(self, text: str, source_widget=None) -> str:
        """
        Traite le contenu collé et nettoie les extensions de fichiers
        
        Args:
            text: Texte collé
            source_widget: Widget source (pour les dialogues)
            
        Returns:
            str: Texte nettoyé
        """
        if not text or not self._contains_file_extensions(text):
            return text
            
        app_logger.debug(f"Détection d'extensions dans le texte collé: '{text[:50]}...'")
        
        # Analyser les extensions présentes
        extensions_found = self._find_file_extensions(text)
        if not extensions_found:
            return text
            
        # Décider du remplacement à appliquer
        replacement = self._get_replacement_choice(extensions_found, source_widget)
        if replacement is None:
            return text  # Utilisateur a annulé
            
        # Appliquer le nettoyage
        cleaned_text = self._clean_text(text, replacement)
        
        if cleaned_text != text:
            self.text_cleaned.emit(text, cleaned_text)
            app_logger.info(f"Texte nettoyé: '{text}' → '{cleaned_text}'")
            
        return cleaned_text
    
    def _contains_file_extensions(self, text: str) -> bool:
        """Vérifie si le texte contient des extensions de fichiers"""
        pattern = r'\.(?:' + '|'.join(ext[1:] for ext in self._user_extensions) + r')\b'
        return bool(re.search(pattern, text, re.IGNORECASE))
    
    def _find_file_extensions(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Trouve toutes les extensions de fichiers dans le texte
        
        Returns:
            List[Tuple[str, int, int]]: Liste de (extension, position_début, position_fin)
        """
        extensions_found = []
        pattern = r'\.(?:' + '|'.join(ext[1:] for ext in self._user_extensions) + r')\b'
        
        for match in re.finditer(pattern, text, re.IGNORECASE):
            ext = match.group().lower()
            start, end = match.span()
            
            # Vérifier s'il y a un espace après l'extension
            if end < len(text) and text[end] == ' ':
                end += 1
                
            extensions_found.append((ext, start, end))
            
        return extensions_found
    
    def _get_replacement_choice(self, extensions_found: List[Tuple[str, int, int]], 
                               source_widget=None) -> Optional[str]:
        """
        Détermine le remplacement à appliquer selon les préférences utilisateur
        
        Returns:
            str: Type de remplacement ('or', 'and', 'space', 'remove') ou None si annulé
        """
        # Créer une clé pour mémoriser le choix
        ext_key = '|'.join(sorted(set(ext for ext, _, _ in extensions_found)))
        
        # Si on a déjà mémorisé un choix pour ces extensions
        if not self._ask_confirmation or ext_key in self._user_choice_memory:
            return self._user_choice_memory.get(ext_key, 'or')
        
        # Demander confirmation à l'utilisateur
        choice = self._show_replacement_dialog(extensions_found, source_widget)
        
        # Mémoriser le choix si demandé
        if choice and self._remember_choice:
            self._user_choice_memory[ext_key] = choice
            
        return choice
    
    def _show_replacement_dialog(self, extensions_found: List[Tuple[str, int, int]], 
                                source_widget=None) -> Optional[str]:
        """Affiche le dialogue de choix de remplacement"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox
        
        class ReplacementDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Nettoyage automatique du collage")
                self.setModal(True)
                self.choice = None
                self.setup_ui()
                
            def setup_ui(self):
                layout = QVBoxLayout()
                
                # Message explicatif
                extensions_text = ", ".join(set(ext for ext, _, _ in extensions_found))
                message = QLabel(f"Extensions détectées: {extensions_text}\n\n"
                               "Comment souhaitez-vous les remplacer ?")
                layout.addWidget(message)
                
                # Boutons de choix
                buttons_layout = QVBoxLayout()
                
                btn_or = QPushButton("Remplacer par || (OU logique)")
                btn_or.clicked.connect(lambda: self.set_choice('or'))
                buttons_layout.addWidget(btn_or)
                
                btn_and = QPushButton("Remplacer par && (ET logique)")
                btn_and.clicked.connect(lambda: self.set_choice('and'))
                buttons_layout.addWidget(btn_and)
                
                btn_space = QPushButton("Remplacer par un espace")
                btn_space.clicked.connect(lambda: self.set_choice('space'))
                buttons_layout.addWidget(btn_space)
                
                btn_remove = QPushButton("Supprimer complètement")
                btn_remove.clicked.connect(lambda: self.set_choice('remove'))
                buttons_layout.addWidget(btn_remove)
                
                layout.addLayout(buttons_layout)
                
                # Case à cocher pour mémoriser
                self.remember_checkbox = QCheckBox("Mémoriser ce choix pour ces extensions")
                self.remember_checkbox.setChecked(True)
                layout.addWidget(self.remember_checkbox)
                
                # Bouton Annuler
                cancel_layout = QHBoxLayout()
                cancel_layout.addStretch()
                btn_cancel = QPushButton("Annuler")
                btn_cancel.clicked.connect(self.reject)
                cancel_layout.addWidget(btn_cancel)
                layout.addLayout(cancel_layout)
                
                self.setLayout(layout)
                
            def set_choice(self, choice):
                self.choice = choice
                self.accept()
        
        dialog = ReplacementDialog(source_widget)
        if dialog.exec_() == QDialog.Accepted:
            # Mettre à jour la préférence de mémorisation
            if hasattr(dialog, 'remember_checkbox'):
                self._remember_choice = dialog.remember_checkbox.isChecked()
            return dialog.choice
            
        return None
    
    def _clean_text(self, text: str, replacement_type: str) -> str:
        """
        Nettoie le texte en remplaçant les extensions
        
        Args:
            text: Texte original
            replacement_type: Type de remplacement ('or', 'and', 'space', 'remove')
            
        Returns:
            str: Texte nettoyé
        """
        if replacement_type not in self._replacement_options:
            return text
            
        replacement_str = self._replacement_options[replacement_type]
        
        # Pattern pour capturer extension + espace optionnel en fin de mot
        pattern = r'\.(?:' + '|'.join(re.escape(ext[1:]) for ext in self._user_extensions) + r')\b(\s*)'
        
        def replace_func(match):
            space_after = match.group(1)
            
            if replacement_type == 'remove':
                # Garder un seul espace s'il y en avait un
                return ' ' if space_after else ''
            elif replacement_type == 'space':
                # Remplacer par un espace
                return ' '
            else:
                # Remplacer par || ou && selon le choix
                # Si en fin de chaîne ou si pas d'espace après, pas de séparateur supplémentaire
                if not space_after:
                    return ''  # Extension en fin de chaîne, juste supprimer
                else:
                    return ' ' + replacement_str + ' '
        
        cleaned = re.sub(pattern, replace_func, text, flags=re.IGNORECASE)
        
        # Nettoyer les espaces multiples et les séparateurs en début/fin
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r'^(\|\||\&\&)\s*', '', cleaned)  # Début
        cleaned = re.sub(r'\s*(\|\||\&\&)$', '', cleaned)  # Fin
        
        return cleaned
    
    def configure_extensions(self, extensions: List[str]):
        """Configure la liste des extensions à détecter"""
        self._user_extensions = [ext.lower() if ext.startswith('.') else f'.{ext.lower()}' 
                                for ext in extensions]
        app_logger.debug(f"Extensions configurées: {self._user_extensions}")
    
    def configure_defaults(self, default_replacement: str = '||', 
                         ask_confirmation: bool = True,
                         remember_choice: bool = True):
        """Configure les paramètres par défaut du service"""
        if default_replacement in ['||', '&&', ' ', '']:
            self._default_replacement = default_replacement
        self._ask_confirmation = ask_confirmation
        self._remember_choice = remember_choice
        
        app_logger.debug(f"Configuration mise à jour: remplacement={default_replacement}, "
                        f"confirmation={ask_confirmation}, mémorisation={remember_choice}")
    
    def clear_memory(self):
        """Efface la mémoire des choix utilisateur"""
        self._user_choice_memory.clear()
        app_logger.debug("Mémoire des choix utilisateur effacée")
    
    def get_memory_stats(self) -> Dict[str, str]:
        """Retourne les statistiques de la mémoire des choix"""
        return {
            ext_key: self._replacement_options.get(choice, choice)
            for ext_key, choice in self._user_choice_memory.items()
        }