"""
Service d'interaction utilisateur - Phase 2.13
Extrait de main_refactored.py pour centraliser la logique d'interaction avec l'utilisateur

Responsabilités:
- Gestion des dialogues de confirmation, erreur et information
- Historique des actions utilisateur avec formatage HTML
- Mise à jour des compteurs et indicateurs
- Interface standardisée pour toutes les interactions utilisateur
"""

from typing import Optional, List
from datetime import datetime
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer

from src.core.config import Config
from src.core.logger import app_logger

class UserInteractionService:
    """
    Service spécialisé pour les interactions avec l'utilisateur
    
    Responsabilités:
    - Dialogues de confirmation, erreur et information
    - Gestion de l'historique des actions avec formatage HTML
    - Mise à jour des compteurs de lignes et indicateurs de performance
    - Messages temporisés dans la barre de statut
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    def show_error(self, message: str) -> None:
        """Afficher une erreur"""
        QMessageBox.critical(self.main_window, "Erreur", message)

    def show_info(self, message: str) -> None:
        """Afficher une information"""
        QMessageBox.information(self.main_window, "Information", message)
    
    def show_confirmation(self, title: str, message: str, default_yes: bool = False) -> bool:
        """Afficher une confirmation avec support des raccourcis clavier (Entrée/Échap)"""
        msg_box = QMessageBox(self.main_window)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)
        
        # Créer les boutons
        yes_btn = msg_box.addButton("Oui", QMessageBox.YesRole)
        no_btn = msg_box.addButton("Non", QMessageBox.NoRole)
        
        # Configurer le bouton par défaut
        if default_yes:
            msg_box.setDefaultButton(yes_btn)
            yes_btn.setDefault(True)
        else:
            msg_box.setDefaultButton(no_btn)
            no_btn.setDefault(True)
        
        # Configurer les raccourcis clavier
        yes_btn.setShortcut("Return")  # Entrée
        no_btn.setShortcut("Escape")   # Échap
        
        # Afficher et récupérer le résultat
        result = msg_box.exec_()
        return msg_box.clickedButton() == yes_btn
    
    def show_save_confirmation(self, title: str, message: str) -> str:
        """Afficher une confirmation Oui/Non/Annuler avec raccourcis clavier"""
        msg_box = QMessageBox(self.main_window)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)
        
        # Créer les boutons
        yes_btn = msg_box.addButton("Oui", QMessageBox.YesRole)
        no_btn = msg_box.addButton("Non", QMessageBox.NoRole) 
        cancel_btn = msg_box.addButton("Annuler", QMessageBox.RejectRole)
        
        # Configurer le bouton par défaut
        msg_box.setDefaultButton(yes_btn)
        yes_btn.setDefault(True)
        
        # Configurer les raccourcis clavier
        yes_btn.setShortcut("Return")  # Entrée pour Oui (sauvegarder)
        cancel_btn.setShortcut("Escape")  # Échap pour Annuler
        # N pour Non
        no_btn.setShortcut("N")
        
        # Afficher et récupérer le résultat
        result = msg_box.exec_()
        clicked_button = msg_box.clickedButton()
        
        if clicked_button == yes_btn:
            return "yes"
        elif clicked_button == no_btn:
            return "no"
        else:  # cancel_btn ou fermeture
            return "cancel"

    def update_counter(self) -> None:
        """Mettre à jour le compteur de lignes via TableController"""
        displayed_count = self.main_window.table.rowCount()
        
        # Utiliser le size_label du TableController si disponible
        if hasattr(self.main_window, 'table_controller') and hasattr(self.main_window.table_controller, 'size_label') and self.main_window.table_controller.size_label:
            if hasattr(self.main_window, 'total_rows') and self.main_window.use_pagination and self.main_window.total_rows > Config.MAX_DISPLAY_ROWS:
                self.main_window.table_controller.size_label.setText(f"Affichées : {displayed_count} / Total : {self.main_window.total_rows:,}")
            else:
                self.main_window.table_controller.size_label.setText(f"Lignes : {displayed_count:,}")
        # Fallback sur counter_label si il existe encore
        elif hasattr(self.main_window, 'counter_label'):
            if hasattr(self.main_window, 'total_rows') and self.main_window.use_pagination and self.main_window.total_rows > Config.MAX_DISPLAY_ROWS:
                self.main_window.counter_label.setText(f"Affichées : {displayed_count} / Total : {self.main_window.total_rows:,}")
            else:
                self.main_window.counter_label.setText(f"Lignes : {displayed_count:,}")

    def add_to_history(self, message: str) -> None:
        """Ajouter un message à l'historique"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Initialiser ou récupérer la liste des messages d'historique
        if not hasattr(self.main_window, '_history_messages'):
            self.main_window._history_messages = []
        
        # Appliquer le formatage spécialisé pour les messages d'import
        formatted_message = self._format_message_for_history_original(message, timestamp)
        
        # Ajouter le nouveau message au début de la liste
        self.main_window._history_messages.insert(0, formatted_message)
        
        # Limiter à 50 entrées
        if len(self.main_window._history_messages) > 50:
            self.main_window._history_messages = self.main_window._history_messages[:50]
        
        # Reconstruire tout le HTML
        html_content = self._build_history_html()
        
        # Mettre à jour l'affichage (utiliser history_list comme dans l'original)
        if hasattr(self.main_window, 'history_list'):
            self.main_window.history_list.setHtml(html_content)
            # Garder le scroll en haut pour voir les messages récents
            cursor = self.main_window.history_list.textCursor()
            cursor.movePosition(cursor.Start)
            self.main_window.history_list.setTextCursor(cursor)

    def _format_message_for_history(self, message: str, timestamp: str) -> str:
        """Formater un message pour l'historique avec gestion spécialisée des imports"""
        
        # Couleur par défaut pour les messages normaux
        message_color = Config.Colors.BLACK
        
        # Déterminer la couleur selon le type de message
        if any(keyword in message.lower() for keyword in ["erreur", "error", "échec", "failed"]):
            message_color = Config.Colors.DANGER  # Rouge pour erreurs
        elif any(keyword in message.lower() for keyword in ["succès", "success", "terminé", "completed", "ajouté", "added"]):
            message_color = Config.Colors.SUCCESS  # Vert pour succès
        elif any(keyword in message.lower() for keyword in ["warning", "attention", "avertissement"]):
            message_color = Config.Colors.WARNING  # Orange pour avertissements
        elif any(keyword in message.lower() for keyword in ["import", "export", "fichier", "file"]):
            message_color = Config.Colors.INFO  # Bleu pour opérations fichiers
        
        return f'<p class="message-block"><span class="timestamp">[{timestamp}]</span> <span class="message" style="color: {message_color};">{message}</span></p>'

    def _build_history_html(self) -> str:
        """Construire le HTML complet de l'historique - Compatible avec l'ancien format"""
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 12px; margin: 4px; padding: 4px; }}
        p {{ margin: 1px 0; line-height: 1.0; }}
        p.message-block {{ margin: 1px 0; line-height: 1.0; }}
        p.separator {{ margin: 10px 0 5px 0; }}
        .timestamp {{ color: {Config.Colors.TEXT_MUTED}; }}
        .message {{ color: {Config.Colors.BLACK}; }}
        .indented {{ margin-left: 20px; }}
        .import-header {{ font-weight: bold; color: {Config.Colors.INFO_LIGHT}; }}
        .import-section {{ margin-left: 20px; color: {Config.Colors.TEXT_SECONDARY}; }}
        .import-summary {{ margin-left: 20px; color: {Config.Colors.INFO_LIGHT}; font-weight: 500; }}
        .entry-separator {{ height: 8px; margin: 4px 0; }}
    </style>
</head>
<body>
"""
        
        # Ajouter tous les messages avec le même format que l'original
        for i, msg in enumerate(self.main_window._history_messages):
            # Séparer timestamp et contenu pour styling
            if msg.startswith('[') and '] ' in msg:
                parts = msg.split('] ', 1)
                timestamp_part = parts[0] + ']'
                content_part = parts[1] if len(parts) > 1 else ''
                # Convertir les retours à la ligne en HTML et appliquer l'indentation CSS
                content_part = self._apply_css_indentation(content_part)
                # Cadre rouge (timestamp) : bien séparé du contenu suivant  
                html_content += f"<p class='separator'><span class='timestamp'>{timestamp_part}</span> <span class='message'>{content_part}</span></p>\n"
            else:
                # Convertir les retours à la ligne en HTML avec interligne minimal et indentation CSS
                msg_html = self._apply_css_indentation(msg)
                html_content += f"<p class='message-block'>{msg_html}</p>\n"
            
            # CORRECTION: Réduire l'espacement entre entrées (1 ligne au lieu de 2)
            # Pas de <br> supplémentaire - espacement géré par CSS
        
        html_content += """</body>
</html>"""
        return html_content

    def _apply_css_indentation(self, content: str) -> str:
        """Appliquer l'indentation avec des espaces non-sécables pour les lignes ==>"""
        # CORRECTION: Remplacer les \\n littéraux par de vrais retours à la ligne
        content = content.replace('\\n', '\n')
        lines = content.split('\n')
        processed_lines = []
        
        for line in lines:
            stripped_line = line.strip()
            
            if (stripped_line.startswith('==> ') or 
                stripped_line.startswith('Créés :') or 
                stripped_line.startswith('Complétion automatique :') or 
                stripped_line.startswith('À compléter :') or 
                stripped_line.startswith('Doublon ignoré :') or 
                stripped_line.startswith('Nouvelles :') or 
                stripped_line.startswith('Déjà associées :')):
                # Utiliser des espaces non-sécables pour l'indentation
                processed_lines.append(f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{line.strip()}')
            else:
                processed_lines.append(line)
        
        # Convertir les retours à la ligne en HTML
        return '<br>'.join(processed_lines)
    
    def _format_message_for_history_original(self, message: str, timestamp: str) -> str:
        """Formater les messages pour un affichage optimisé dans l'historique - Version originale"""
        
        # Si c'est un message d'import PDF, appliquer le formatage spécialisé
        if "📊 Import" in message:
            lines = message.strip().split('\n')
            formatted_lines = []
            
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                
                # En-tête d'import : garder tel quel mais sans timestamp redondant
                if line.startswith("📊 Import"):
                    formatted_lines.append(line)
                    continue
                
                # Messages PDF : enlever les préfixes de fichier et nettoyer
                if "📄 Fichier PDF" in line and "lignes extraites" in line:
                    # Format: "📄 Fichier PDF filename.pdf: N lignes extraites"
                    # On veut garder juste cette information
                    formatted_lines.append(line)
                    continue
                
                # Lignes traitées : ajouter le préfixe ==>
                if line.startswith("Lignes traitées"):
                    formatted_lines.append(f"==> {line}")
                    continue
                
                # Titres de sections : ajouter interligne seulement avant "Appareils :"
                if line.endswith("Appareils :"):
                    formatted_lines.append("")  # Interligne avant première section
                    formatted_lines.append(line)
                    continue
                elif line.endswith("Associations de pièce :"):
                    formatted_lines.append(line)  # Pas d'interligne supplémentaire
                    continue
                
                # Éléments de synthèse : garder tels quels (l'indentation sera gérée par CSS)
                if line.strip().startswith("==> ") or line.strip().startswith("Créés :") or line.strip().startswith("Complétion automatique :"):
                    formatted_lines.append(line.strip())
                    continue
                
                # Autres lignes : garder telles quelles
                formatted_lines.append(line)
            
            # Reconstruire le message avec le formatage appliqué
            formatted_content = '\n'.join(formatted_lines)
            return f"[{timestamp}] {formatted_content}"
        
        # CORRECTION: Pour les autres messages, traiter les \n littéraux
        # Remplacer les \n littéraux par de vrais retours à la ligne
        processed_message = message.replace('\\n', '\n')
        return f"[{timestamp}] {processed_message}"

    def show_status_message(self, message: str, timeout: int = None) -> None:
        """Afficher un message temporaire dans la barre de statut"""
        if timeout is None:
            timeout = Config.STATUS_MESSAGE_TIMEOUT
            
        if hasattr(self.main_window, 'statusbar'):
            self.main_window.statusbar.showMessage(message, timeout)

    def show_performance_indicator(self, message: str, duration_ms: Optional[int] = None) -> None:
        """Afficher un indicateur de performance"""
        if hasattr(self.main_window, 'perf_label'):
            if duration_ms is not None:
                perf_message = f"⚡ {message} ({duration_ms}ms)"
            else:
                perf_message = f"⚡ {message}"
            
            self.main_window.perf_label.setText(perf_message)
            
            # Remettre "Prêt" après quelques secondes
            if duration_ms is not None:
                QTimer.singleShot(3000, lambda: self._reset_performance_indicator())

    def _reset_performance_indicator(self) -> None:
        """Remettre l'indicateur de performance à "Prêt" """
        if hasattr(self.main_window, 'perf_label'):
            self.main_window.perf_label.setText("⚡ Prêt")

    def clear_history(self) -> None:
        """Vider l'historique des messages"""
        if hasattr(self.main_window, '_history_messages'):
            self.main_window._history_messages.clear()
            
        if hasattr(self.main_window, 'history_list'):
            empty_html = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 12px; margin: 4px; padding: 4px; }}
    </style>
</head>
<body>
    <p style="color: {Config.Colors.TEXT_MUTED};">Historique vide</p>
</body>
</html>"""
            self.main_window.history_list.setHtml(empty_html)

    def get_history_count(self) -> int:
        """Obtenir le nombre de messages dans l'historique"""
        if hasattr(self.main_window, '_history_messages'):
            return len(self.main_window._history_messages)
        return 0