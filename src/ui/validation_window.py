"""
Fenêtre interactive de validation et détection d'incohérences
"""

import re
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTextEdit, QWidget, QTabWidget, QTreeWidget, QTreeWidgetItem
)
from PyQt5.QtCore import Qt

def clean_display_text(text):
    """
    Nettoie le texte pour l'affichage en supprimant les caractères illisibles
    """
    if not text:
        return ""
    
    # Convertir en string si nécessaire
    text = str(text)
    
    # Supprimer les caractères de contrôle (sauf retour à la ligne et tabulation)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    
    # Remplacer les caractères non-UTF8 par un caractère de substitution
    try:
        text = text.encode('utf-8', errors='replace').decode('utf-8')
    except:
        text = "???"
    
    # Supprimer les espaces multiples
    text = re.sub(r'\s+', ' ', text)
    
    # Nettoyer les caractères invisibles ou problématiques
    text = text.strip()
    
    return text

class ValidationWindow(QDialog):
    """Fenêtre interactive de validation et détection d'incohérences"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("🔍 Validation et Incohérences - Interface Interactive")
        self.resize(1000, 700)
        self.setModal(False)  # Permettre interaction avec la fenêtre principale
        
        # Données
        self.validation_data = {}
        self.inconsistency_data = {}
        self.current_filter = "all"
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        """Initialiser l'interface"""
        layout = QVBoxLayout(self)
        
        # En-tête avec statistiques
        header_layout = QHBoxLayout()
        
        self.stats_label = QLabel("📊 Chargement des données...")
        self.stats_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #007bff; padding: 10px;")
        header_layout.addWidget(self.stats_label)
        
        header_layout.addStretch()
        
        # Bouton rafraîchir
        refresh_btn = QPushButton("🔄 Actualiser")
        refresh_btn.clicked.connect(self._load_data)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Filtres par type d'erreur
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("📂 Filtrer par type:"))
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "Tout afficher",
            "🔧 Problèmes de validation",
            "🔄 Références avec variations",
            "📋 Références en doublon",
            "❌ Champs critiques vides"
        ])
        self.filter_combo.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.filter_combo)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Zone principale avec onglets
        self.tab_widget = QTabWidget()
        
        # Onglet Vue d'ensemble
        self.overview_tab = self._create_overview_tab()
        self.tab_widget.addTab(self.overview_tab, "📊 Vue d'ensemble")
        
        # Onglet Détails
        self.details_tab = self._create_details_tab()
        self.tab_widget.addTab(self.details_tab, "🔍 Détails")
        
        layout.addWidget(self.tab_widget)
        
        # Boutons d'action
        action_layout = QHBoxLayout()
        
        # Raccourcis de recherche (masqués temporairement car redondants avec onglet Détails)
        # search_layout = QVBoxLayout()
        # search_layout.addWidget(QLabel("🔎 Raccourcis de recherche:"))
        # 
        # search_buttons_layout = QHBoxLayout()
        # 
        # search_orphaned_btn = QPushButton("🔗 Pièces orphelines")
        # search_orphaned_btn.clicked.connect(lambda: self._quick_search("orphaned"))
        # search_buttons_layout.addWidget(search_orphaned_btn)
        # 
        # search_duplicates_btn = QPushButton("📋 Doublons")
        # search_duplicates_btn.clicked.connect(lambda: self._quick_search("duplicates"))
        # search_buttons_layout.addWidget(search_duplicates_btn)
        # 
        # search_empty_btn = QPushButton("❌ Champs vides")
        # search_empty_btn.clicked.connect(lambda: self._quick_search("empty"))
        # search_buttons_layout.addWidget(search_empty_btn)
        # 
        # search_inconsistencies_btn = QPushButton("⚠️ Incohérences")
        # search_inconsistencies_btn.clicked.connect(lambda: self._quick_search("inconsistencies"))
        # search_buttons_layout.addWidget(search_inconsistencies_btn)
        # 
        # search_layout.addLayout(search_buttons_layout)
        # action_layout.addLayout(search_layout)
        
        action_layout.addStretch()
        
        # Bouton fermer
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.close)
        action_layout.addWidget(close_btn)
        
        layout.addLayout(action_layout)
    
    def _create_overview_tab(self):
        """Créer l'onglet vue d'ensemble"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Zone de résumé
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(200)
        self.summary_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 12px;
                font-family: 'Monaco', 'Consolas', monospace;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.summary_text)
        
        # Graphiques ou statistiques visuelles
        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        
        # Cartes de statistiques
        self.validation_card = self._create_stat_card("🔧 Validation", "0", "#28a745")
        self.inconsistency_card = self._create_stat_card("🔄 Incohérences", "0", "#ffc107")
        self.critical_card = self._create_stat_card("❌ Critiques", "0", "#dc3545")
        
        stats_layout.addWidget(self.validation_card)
        stats_layout.addWidget(self.inconsistency_card)
        stats_layout.addWidget(self.critical_card)
        
        layout.addWidget(stats_widget)
        
        return widget
    
    def _create_details_tab(self):
        """Créer l'onglet détails"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Liste détaillée des problèmes
        self.details_tree = QTreeWidget()
        self.details_tree.setHeaderLabels(["Type", "Description", "Nombre", "Actions"])
        self.details_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        layout.addWidget(self.details_tree)
        
        return widget
    
    def _create_stat_card(self, title, value, color):
        """Créer une carte de statistique"""
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                margin: 5px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #6c757d;")
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")
        layout.addWidget(value_label)
        
        # Stocker la référence du label pour mise à jour
        widget.value_label = value_label
        
        return widget
    
    def _load_data(self):
        """Charger les données de validation et incohérences"""
        try:
            # 1. Validation de la base de données
            issues = self.parent_window.db_manager.validate_database()
            self.validation_data = issues
            
            # 2. Détection des incohérences - requête simplifiée
            query = """
            SELECT ref_modele, type, manufacturer, COUNT(*) as count
            FROM appareils 
            WHERE ref_modele IS NOT NULL AND ref_modele != ''
            GROUP BY ref_modele
            HAVING COUNT(DISTINCT type || '|' || manufacturer) > 1
            ORDER BY ref_modele
            """
            
            try:
                inconsistency_results = self.parent_window.db_manager.execute_custom_query(query)
                self.inconsistency_data = {}
                
                if inconsistency_results:
                    # Pour chaque référence avec incohérences, récupérer les variations
                    for row in inconsistency_results:
                        ref_modele = row[0]
                        clean_ref_modele = clean_display_text(ref_modele)
                        
                        # Récupérer toutes les variations pour cette référence
                        detail_query = """
                        SELECT DISTINCT type, manufacturer, COUNT(*) as count
                        FROM appareils 
                        WHERE ref_modele = ?
                        GROUP BY type, manufacturer
                        ORDER BY count DESC
                        """
                        variations = self.parent_window.db_manager.execute_custom_query(detail_query, [ref_modele])
                        
                        if variations and len(variations) > 1:  # Seulement s'il y a vraiment des variations
                            self.inconsistency_data[clean_ref_modele] = []
                            for type_val, manufacturer, count in variations:
                                self.inconsistency_data[clean_ref_modele].append({
                                    'type': clean_display_text(type_val) or '(vide)',
                                    'manufacturer': clean_display_text(manufacturer) or '(vide)',
                                    'count': count
                                })
                        
            except Exception as e:
                app_logger.error("Erreur", e)
                self.inconsistency_data = {}
            
            self._update_display()
            
        except Exception as e:
            if hasattr(self.parent_window, '_show_error'):
                self.parent_window._show_error(f"Erreur lors du chargement des données: {e}")
    
    def _update_display(self):
        """Mettre à jour l'affichage"""
        # Mise à jour des statistiques
        total_validation = sum(self.validation_data.values()) if self.validation_data else 0
        total_inconsistencies = len(self.inconsistency_data) if self.inconsistency_data else 0
        total_critical = self.validation_data.get('empty_critical', 0) if self.validation_data else 0
        
        self.validation_card.value_label.setText(str(total_validation))
        self.inconsistency_card.value_label.setText(str(total_inconsistencies))
        self.critical_card.value_label.setText(str(total_critical))
        
        # Mise à jour du label des stats
        self.stats_label.setText(f"📊 {total_validation} problèmes de validation • {total_inconsistencies} incohérences • {total_critical} critiques")
        
        # Mise à jour du résumé
        self._update_summary()
        
        # Mise à jour des détails
        self._update_details()
    
    def _update_summary(self):
        """Mettre à jour le résumé"""
        lines = []
        lines.append("🔍 RAPPORT DE VALIDATION ET INCOHÉRENCES")
        lines.append("=" * 50)
        lines.append("")
        
        # Validation
        lines.append("📋 VALIDATION DE LA BASE:")
        if self.validation_data.get('duplicate_refs', 0) > 0:
            lines.append(f"  📋 {self.validation_data['duplicate_refs']} référence(s) en doublon")
            
            # Lister les références en doublon (par ref_modele)
            try:
                duplicates = self.parent_window.db_manager.get_duplicate_ref_modeles()
                if duplicates:
                    lines.append("     Références modèle dupliquées :")
                    for ref_modele, count in duplicates[:10]:  # Limiter à 10
                        clean_ref = clean_display_text(ref_modele)
                        lines.append(f"     • '{clean_ref}' ({count} appareils)")
                    if len(duplicates) > 10:
                        lines.append(f"     ... et {len(duplicates) - 10} autres références")
            except Exception as e:
                lines.append(f"     Erreur lors de la récupération des doublons: {e}")
        if self.validation_data.get('empty_critical', 0) > 0:
            lines.append(f"  ❌ {self.validation_data['empty_critical']} appareil(s) sans type ni fabricant")
        
        if sum(self.validation_data.values()) == 0:
            lines.append("  ✅ Aucun problème de validation")
        
        lines.append("")
        
        # Incohérences
        lines.append("📋 INCOHÉRENCES:")
        if self.inconsistency_data and len(self.inconsistency_data) > 0:
            lines.append(f"  🔍 {len(self.inconsistency_data)} référence(s) avec valeurs différentes")
            lines.append("")
            
            # Détailler les incohérences
            for ref_modele, variations in list(self.inconsistency_data.items())[:5]:  # Limiter à 5 pour l'aperçu
                clean_ref = clean_display_text(ref_modele)
                lines.append(f"  - '{clean_ref}' -> {len(variations)} variation(s)")
                for variation in variations[:2]:  # Limiter à 2 variations par référence
                    clean_type = clean_display_text(variation['type'])
                    clean_manufacturer = clean_display_text(variation['manufacturer'])
                    lines.append(f"      * {clean_type} | {clean_manufacturer} ({variation['count']} occ.)")
            
            if len(self.inconsistency_data) > 5:
                lines.append(f"  ... et {len(self.inconsistency_data) - 5} autres références")
        else:
            lines.append("  ✅ Aucune incohérence détectée")
        
        self.summary_text.setPlainText("\n".join(lines))
    
    def _update_details(self):
        """Mettre à jour l'arbre des détails"""
        self.details_tree.clear()
        
        # Appliquer le filtrage selon la sélection
        show_validation = self.current_filter in ["Tout afficher", "🔧 Problèmes de validation", "📋 Références en doublon", "❌ Champs critiques vides"]
        show_inconsistencies = self.current_filter in ["Tout afficher", "🔄 Références avec variations"]
        
        # Ajouter les problèmes de validation
        if show_validation and sum(self.validation_data.values()) > 0:
            validation_item = QTreeWidgetItem(["🔧 Problèmes de validation", "", str(sum(self.validation_data.values())), ""])
            
            # Filtres spécifiques
            show_duplicates = self.current_filter in ["Tout afficher", "🔧 Problèmes de validation", "📋 Références en doublon"]
            show_empty = self.current_filter in ["Tout afficher", "🔧 Problèmes de validation", "❌ Champs critiques vides"]
            
            if show_duplicates and self.validation_data.get('duplicate_refs', 0) > 0:
                duplicate_item = QTreeWidgetItem([
                    "📋 Références en doublon", 
                    f"{self.validation_data['duplicate_refs']} références dupliquées", 
                    str(self.validation_data['duplicate_refs']), 
                    "Rechercher"
                ])
                
                # Ajouter le détail des références en doublon (par ref_modele)
                try:
                    duplicates = self.parent_window.db_manager.get_duplicate_ref_modeles()
                    for ref_modele, count in duplicates[:50]:  # Limiter à 50 pour éviter surcharge
                        clean_ref = clean_display_text(ref_modele)
                        
                        duplicate_detail = QTreeWidgetItem([
                            f"📋 {clean_ref}",
                            f"{count} appareils avec cette référence",
                            str(count),
                            "Rechercher"
                        ])
                        duplicate_item.addChild(duplicate_detail)
                    
                    if len(duplicates) > 50:
                        more_item = QTreeWidgetItem([
                            f"... et {len(duplicates) - 50} autres références",
                            "",
                            "",
                            ""
                        ])
                        duplicate_item.addChild(more_item)
                        
                except Exception as e:
                    error_item = QTreeWidgetItem([
                        "Erreur lors du chargement des détails",
                        str(e),
                        "",
                        ""
                    ])
                    duplicate_item.addChild(error_item)
                
                validation_item.addChild(duplicate_item)
            
            if show_empty and self.validation_data.get('empty_critical', 0) > 0:
                empty_item = QTreeWidgetItem([
                    "❌ Champs critiques vides", 
                    f"{self.validation_data['empty_critical']} appareils sans type ni fabricant", 
                    str(self.validation_data['empty_critical']), 
                    "Rechercher"
                ])
                validation_item.addChild(empty_item)
            
            # N'ajouter le nœud parent que s'il a des enfants
            if validation_item.childCount() > 0:
                self.details_tree.addTopLevelItem(validation_item)
                validation_item.setExpanded(True)
        
        # Ajouter les incohérences
        if show_inconsistencies and self.inconsistency_data:
            inconsistency_item = QTreeWidgetItem([
                "⚠️ Incohérences", 
                f"{len(self.inconsistency_data)} références avec variations", 
                str(len(self.inconsistency_data)), 
                ""
            ])
            
            for ref_modele, variations in self.inconsistency_data.items():
                clean_ref = clean_display_text(ref_modele)
                ref_item = QTreeWidgetItem([
                    f"{clean_ref}", 
                    f"{len(variations)} variations trouvées", 
                    str(len(variations)), 
                    "Rechercher"
                ])
                inconsistency_item.addChild(ref_item)
            
            self.details_tree.addTopLevelItem(inconsistency_item)
            inconsistency_item.setExpanded(True)
        
        # Ajuster les colonnes
        for i in range(4):
            self.details_tree.resizeColumnToContents(i)
    
    def _apply_filter(self, filter_text):
        """Appliquer un filtre"""
        self.current_filter = filter_text
        self._update_details()
    
    def _quick_search(self, search_type):
        """Effectuer une recherche rapide dans la fenêtre principale"""
        try:
            if search_type == "duplicates":
                # Rechercher les doublons - recherche générale
                self.parent_window.search_input.clear()
                self.parent_window.statusbar.showMessage("📋 Voir l'onglet Détails pour les références en doublon", 3000)
                
            elif search_type == "empty":
                # Rechercher les champs vides en utilisant le filtre incomplet
                if hasattr(self.parent_window, 'incomplete_filter_btn'):
                    self.parent_window.incomplete_filter_btn.click()
                    self.parent_window.statusbar.showMessage("❌ Filtrage des lignes incomplètes activé", 3000)
                
            elif search_type == "inconsistencies":
                # Afficher la première incohérence trouvée
                if self.inconsistency_data:
                    first_ref = list(self.inconsistency_data.keys())[0]
                    clean_first_ref = clean_display_text(first_ref)
                    self.parent_window.search_input.setText(clean_first_ref)
                    self.parent_window.load_data(first_ref)
                    self.parent_window.statusbar.showMessage(f"🔍 Recherche de '{first_ref}' (première incohérence)", 3000)
                
        except Exception as e:
            if hasattr(self.parent_window, '_show_error'):
                self.parent_window._show_error(f"Erreur lors de la recherche: {e}")
    
    def _on_item_double_clicked(self, item, column):
        """Gérer le double-clic sur un élément"""
        if column == 3 and item.text(3) == "Rechercher":
            # Effectuer une recherche basée sur le type d'élément
            item_type = item.text(0)
            if "doublon" in item_type:
                self._quick_search("duplicates")
            elif "vides" in item_type:
                self._quick_search("empty")
            elif item.parent() and ("Incohérences" in item.parent().text(0) or "doublon" in item.parent().text(0)):
                # Recherche d'une référence spécifique (incohérences ou doublons)
                ref_modele = item.text(0).replace("📋 ", "")
                clean_ref_modele = clean_display_text(ref_modele)
                self.parent_window.search_input.setText(clean_ref_modele)
                self.parent_window.load_data(clean_ref_modele)
                self.parent_window.statusbar.showMessage(f"🔍 Recherche de '{clean_ref_modele}'", 3000)
