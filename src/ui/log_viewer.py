"""
Interface de visualisation des logs pour l'application 1001pieces
Permet d'analyser les logs en temps réel et de diagnostiquer les problèmes
"""

from .qt_imports import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, 
    QPushButton, QLabel, QSpinBox, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit
)
from .qt_imports import QTimer, Qt
from .qt_imports import QFont, QTextCharFormat, QColor
import json
import os
from datetime import datetime

from ..core.config import Config

from src.core.logger import app_logger
from ..utils.error_handler import handle_log_viewer_errors

class LogViewer(QDialog):
    """Visualiseur de logs avec filtrage et mise à jour en temps réel"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visualiseur de Logs - 1001pieces.com")
        self.setModal(False)
        self.resize(1000, 700)
        
        # Configuration
        self.auto_refresh = True
        self.refresh_interval = 2000  # 2 secondes
        
        self.setup_ui()
        self.setup_timer()
        self.load_logs()
    
    def setup_ui(self):
        """Configurer l'interface utilisateur"""
        layout = QVBoxLayout()
        
        # Barre de contrôle
        control_layout = QHBoxLayout()
        
        # Sélecteur de type de log
        control_layout.addWidget(QLabel("Type de log:"))
        self.log_type_combo = QComboBox()
        self.log_type_combo.addItems(["detailed", "errors", "data_operations"])
        self.log_type_combo.currentTextChanged.connect(self.on_log_type_changed)
        control_layout.addWidget(self.log_type_combo)
        
        # Nombre de lignes
        control_layout.addWidget(QLabel("Lignes:"))
        self.lines_spinbox = QSpinBox()
        self.lines_spinbox.setRange(10, 1000)
        self.lines_spinbox.setValue(100)
        self.lines_spinbox.valueChanged.connect(self.load_logs)
        control_layout.addWidget(self.lines_spinbox)
        
        # Filtre de recherche
        control_layout.addWidget(QLabel("Filtre:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Rechercher dans les logs...")
        self.filter_input.textChanged.connect(self.apply_filter)
        control_layout.addWidget(self.filter_input)
        
        # Boutons
        self.refresh_button = QPushButton("Actualiser")
        self.refresh_button.clicked.connect(self.load_logs)
        control_layout.addWidget(self.refresh_button)
        
        self.auto_refresh_button = QPushButton("Auto-actualisation: ON")
        self.auto_refresh_button.clicked.connect(self.toggle_auto_refresh)
        control_layout.addWidget(self.auto_refresh_button)
        
        self.clear_button = QPushButton("Effacer")
        self.clear_button.clicked.connect(self.clear_logs)
        control_layout.addWidget(self.clear_button)
        
        layout.addLayout(control_layout)
        
        # Onglets pour différentes vues
        self.tabs = QTabWidget()
        
        # Onglet logs bruts
        self.raw_logs_tab = QWidget()
        raw_layout = QVBoxLayout()
        self.raw_logs_text = QTextEdit()
        self.raw_logs_text.setFont(QFont("Courier", 10))
        self.raw_logs_text.setReadOnly(True)
        raw_layout.addWidget(self.raw_logs_text)
        self.raw_logs_tab.setLayout(raw_layout)
        self.tabs.addTab(self.raw_logs_tab, "Logs Bruts")
        
        # Onglet auto-complétion
        self.autocomplete_tab = QWidget()
        autocomplete_layout = QVBoxLayout()
        self.autocomplete_table = QTableWidget()
        self.autocomplete_table.setColumnCount(8)
        self.autocomplete_table.setHorizontalHeaderLabels([
            "Timestamp", "Row ID", "Références", "Correspondances", 
            "Type Avant", "Type Après", "Fabricant Avant", "Fabricant Après"
        ])
        self.autocomplete_table.horizontalHeader().setStretchLastSection(True)
        autocomplete_layout.addWidget(self.autocomplete_table)
        self.autocomplete_tab.setLayout(autocomplete_layout)
        self.tabs.addTab(self.autocomplete_tab, "Auto-complétion")
        
        # Onglet opérations données
        self.data_ops_tab = QWidget()
        data_ops_layout = QVBoxLayout()
        self.data_ops_table = QTableWidget()
        self.data_ops_table.setColumnCount(6)
        self.data_ops_table.setHorizontalHeaderLabels([
            "Timestamp", "Opération", "Table ID", "Champ", "Ancienne Valeur", "Nouvelle Valeur"
        ])
        self.data_ops_table.horizontalHeader().setStretchLastSection(True)
        data_ops_layout.addWidget(self.data_ops_table)
        self.data_ops_tab.setLayout(data_ops_layout)
        self.tabs.addTab(self.data_ops_tab, "Opérations Données")
        
        layout.addWidget(self.tabs)
        
        # Barre de statut
        self.status_label = QLabel("Prêt")
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
    
    def setup_timer(self):
        """Configurer le timer pour l'actualisation automatique"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.load_logs)
        if self.auto_refresh:
            self.timer.start(self.refresh_interval)
    
    def toggle_auto_refresh(self):
        """Basculer l'actualisation automatique"""
        self.auto_refresh = not self.auto_refresh
        
        if self.auto_refresh:
            self.auto_refresh_button.setText("Auto-actualisation: ON")
            self.timer.start(self.refresh_interval)
        else:
            self.auto_refresh_button.setText("Auto-actualisation: OFF")
            self.timer.stop()
    
    def on_log_type_changed(self):
        """Réagir au changement de type de log"""
        self.load_logs()
    
    @handle_log_viewer_errors()
    def load_logs(self, value=None):
        """Charger les logs depuis les fichiers - value accepte argument signal Qt"""
        log_type = self.log_type_combo.currentText()
        lines = self.lines_spinbox.value()

        # Charger les logs bruts
        raw_logs = app_logger.get_recent_logs(log_type, lines)

        # Formatter les logs pour l'affichage dans l'historique
        formatted_logs = self.format_logs_for_display(raw_logs)
        self.raw_logs_text.setPlainText(formatted_logs)

        # Traiter les logs spécialisés
        if log_type == "data_operations":
            self.parse_data_operations_logs(raw_logs)

        self.status_label.setText(f"Logs actualisés: {datetime.now().strftime('%H:%M:%S')}")
    
    def format_logs_for_display(self, raw_logs: str) -> str:
        """Formater les logs pour un affichage optimisé dans l'historique"""
        if not raw_logs.strip():
            return raw_logs
            
        lines = raw_logs.strip().split('\n')
        formatted_lines = []
        in_import_section = False
        
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            
            # Détecter le début d'une section d'import
            if "📊 Import" in line and " | INFO     | " in line:
                in_import_section = True
                timestamp_part = line.split(" | INFO     | ")[0]
                message_part = line.split(" | INFO     | ")[1]
                time_part = timestamp_part.split(",")[0].split(" ")[-1]  # HH:MM:SS
                
                # Ajouter interligne avant nouvelle action et ligne d'en-tête
                formatted_lines.append("")
                formatted_lines.append(f"[{time_part}] {message_part}")
                continue
            
            # Messages PDF dans le contexte d'import
            if in_import_section and "📄 Fichier PDF" in line and "lignes extraites" in line:
                parts = line.split(" | INFO     | ")
                if len(parts) >= 2:
                    formatted_lines.append(parts[1])
                    continue
            
            # Messages PDF hors contexte d'import (normaux)
            if not in_import_section and "📄 Fichier PDF" in line and "lignes extraites" in line:
                parts = line.split(" | INFO     | ")
                if len(parts) >= 2:
                    formatted_lines.append(parts[1])
                    continue
            
            # Lignes traitées dans le contexte d'import
            if in_import_section and "Lignes traitées" in line and " | INFO     | " in line:
                message_part = line.split(" | INFO     | ")[1]
                formatted_lines.append(f"    ==> {message_part}")
                formatted_lines.append("")  # Interligne après lignes traitées
                continue
            
            # Titres de sections dans l'import
            if in_import_section and (line.endswith("Appareils :") or line.endswith("Associations de pièce :")):
                if " | INFO     | " in line:
                    message_part = line.split(" | INFO     | ")[1]
                    formatted_lines.append(message_part)
                else:
                    formatted_lines.append(line)
                continue
            
            # Éléments de synthèse avec indentation
            if in_import_section and "==> " in line and " | INFO     | " in line:
                message_part = line.split(" | INFO     | ")[1]
                formatted_lines.append(f"    {message_part}")
                continue
                
            # Détecter la fin de la section d'import
            if in_import_section and not any(keyword in line for keyword in 
                                           ["📄 Fichier PDF", "Lignes traitées", "Appareils", "Associations", "==> "]):
                in_import_section = False
            
            # Autres messages : garder tel quel
            formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    @handle_log_viewer_errors()
    def parse_data_operations_logs(self, raw_logs):
        """Parser les logs d'opérations sur les données"""
        lines = raw_logs.strip().split('\n')

        # Réinitialiser les tables
        self.autocomplete_table.setRowCount(0)
        self.data_ops_table.setRowCount(0)

        autocomplete_row = 0
        data_ops_row = 0

        for line in lines:
            if not line.strip():
                continue

            # Traitement JSON sécurisé avec méthode dédiée
            result = self._process_log_line_safely(line)
            if result:
                log_type, data = result
                if log_type == "autocomplete":
                    self.add_autocomplete_row(data, autocomplete_row)
                    autocomplete_row += 1
                elif log_type == "data_ops":
                    self.add_data_ops_row(data, data_ops_row)
                    data_ops_row += 1

        # Redimensionner les colonnes
        self.autocomplete_table.resizeColumnsToContents()
        self.data_ops_table.resizeColumnsToContents()
    
    def add_autocomplete_row(self, data, row):
        """Ajouter une ligne à la table d'auto-complétion"""
        self.autocomplete_table.insertRow(row)
        
        # Timestamp
        timestamp = data.get('timestamp', '')[:19]  # Couper les microsecondes
        self.autocomplete_table.setItem(row, 0, QTableWidgetItem(timestamp))
        
        # Row ID
        row_id = str(data.get('row_id', ''))
        self.autocomplete_table.setItem(row, 1, QTableWidgetItem(row_id))
        
        # Références
        search_criteria = data.get('search_criteria', {})
        references = ', '.join(search_criteria.get('references', []))
        self.autocomplete_table.setItem(row, 2, QTableWidgetItem(references))
        
        # Correspondances
        matches = str(data.get('matches_found', 0))
        self.autocomplete_table.setItem(row, 3, QTableWidgetItem(matches))
        
        # Données avant/après
        original = data.get('original_data', {})
        completed = data.get('completed_data', {})
        
        type_before = original.get('type', '')
        type_after = completed.get('type', '')
        manufacturer_before = original.get('manufacturer', '')
        manufacturer_after = completed.get('manufacturer', '')
        
        self.autocomplete_table.setItem(row, 4, QTableWidgetItem(type_before))
        self.autocomplete_table.setItem(row, 5, QTableWidgetItem(type_after))
        self.autocomplete_table.setItem(row, 6, QTableWidgetItem(manufacturer_before))
        self.autocomplete_table.setItem(row, 7, QTableWidgetItem(manufacturer_after))
        
        # Coloration selon le succès
        if not data.get('success', True):
            for col in range(8):
                item = self.autocomplete_table.item(row, col)
                if item:
                    item.setBackground(QColor(*Config.Colors.ERROR_LOG))  # Rouge clair pour erreurs
    
    def add_data_ops_row(self, data, row):
        """Ajouter une ligne à la table des opérations sur les données"""
        self.data_ops_table.insertRow(row)
        
        # Timestamp
        timestamp = data.get('timestamp', '')[:19]
        self.data_ops_table.setItem(row, 0, QTableWidgetItem(timestamp))
        
        # Opération
        operation = data.get('operation', '')
        self.data_ops_table.setItem(row, 1, QTableWidgetItem(operation))
        
        # Table ID
        table_id = str(data.get('table_id', ''))
        self.data_ops_table.setItem(row, 2, QTableWidgetItem(table_id))
        
        # Détails des données
        data_details = data.get('data', {})
        field = data_details.get('field', '')
        old_value = str(data_details.get('old_value', ''))
        new_value = str(data_details.get('new_value', ''))
        
        self.data_ops_table.setItem(row, 3, QTableWidgetItem(field))
        self.data_ops_table.setItem(row, 4, QTableWidgetItem(old_value))
        self.data_ops_table.setItem(row, 5, QTableWidgetItem(new_value))
        
        # Coloration selon le succès
        if not data.get('success', True):
            for col in range(6):
                item = self.data_ops_table.item(row, col)
                if item:
                    item.setBackground(QColor(*Config.Colors.ERROR_LOG))
    
    def apply_filter(self):
        """Appliquer le filtre de recherche"""
        filter_text = self.filter_input.text().lower()
        
        if not filter_text:
            # Recharger tous les logs
            self.load_logs()
            return
        
        # Filtrer les logs bruts
        all_text = self.raw_logs_text.toPlainText()
        filtered_lines = []
        
        for line in all_text.split('\n'):
            if filter_text in line.lower():
                filtered_lines.append(line)
        
        self.raw_logs_text.setPlainText('\n'.join(filtered_lines))
        self.status_label.setText(f"Filtré: {len(filtered_lines)} lignes")
    
    def clear_logs(self):
        """Effacer l'affichage des logs"""
        self.raw_logs_text.clear()
        self.autocomplete_table.setRowCount(0)
        self.data_ops_table.setRowCount(0)
        self.status_label.setText("Logs effacés")
    
    @handle_log_viewer_errors(return_value=None)
    def _process_log_line_safely(self, line):
        """Traiter une ligne de log de manière sécurisée pour extraire les données JSON"""
        # Extraire le JSON de la ligne de log
        if " | AUTO_COMPLETE " in line:
            json_start = line.find('{"timestamp"')
            if json_start != -1:
                json_str = line[json_start:]
                data = json.loads(json_str)
                return ("autocomplete", data)

        elif " | DATA_OP " in line:
            json_start = line.find('{"timestamp"')
            if json_start != -1:
                json_str = line[json_start:]
                data = json.loads(json_str)
                return ("data_ops", data)

        return None

    def closeEvent(self, event):
        """Arrêter le timer lors de la fermeture"""
        if self.timer:
            self.timer.stop()
        event.accept()