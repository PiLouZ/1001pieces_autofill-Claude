# 🔧 1001pieces_autofill - Gestionnaire d'Appareils

Application moderne de gestion d'appareils avec interface PyQt5 avancée, gestion de 523 000+ enregistrements et outils de validation interactifs avec EventDrivenSaveService. **v3.15.1**

## 🚀 Lancement Rapide

### 🖱️ **Le plus simple - Sans terminal**
```bash
# Double-cliquez sur le fichier
1001pieces_autofill.command
```

### ⌨️ **En ligne de commande classique**
```bash
python3 run.py
```

### 🔗 **Lancement direct**
```bash
python3 -m src.ui.main_refactored
```

## 📁 Structure du Projet

```
📦 1001pieces_autofill/
├── 🚀 1001pieces_autofill.command  # Lanceur sans terminal (double-clic)
├── 🚀 run.py                      # Point d'entrée principal  
├── 📋 README.md                   # Ce fichier
├── 📄 requirements.txt            # Dépendances Python
├── 🖼️ logo.webp                   # Logo de l'application
├── 📱 1001pieces_autofill.app     # Bundle macOS (optionnel)
│
├── 📂 src/                        # Code source principal
│   ├── 🔧 core/                   # Configuration centrale
│   │   ├── config.py              # Configuration globale
│   │   └── logger.py              # Système de logs
│   ├── 💾 data/                   # Gestion des données
│   │   ├── database_manager.py    # Gestionnaire BDD optimisé
│   │   ├── data_validator.py      # Validation avancée
│   │   └── data_exporter.py       # Exports multiformats
│   └── 🖥️ ui/                     # Interface utilisateur
│       ├── main_refactored.py     # Application principale
│       ├── validation_window.py   # Fenêtre de validation interactive
│       └── log_viewer.py          # Visualiseur de logs
│
├── 📂 data/                       # Données de l'application
│   └── appareils.db               # Base de données SQLite
│
├── 📂 logs/                       # Fichiers de logs
│   ├── detailed.log               # Logs détaillés
│   ├── errors.log                 # Erreurs système
│   └── data_operations.log        # Opérations sur les données
│
└── 📂 docs/                       # Documentation
    ├── GUIDE_COLLAGE.md           # Guide du collage de données
    └── LANCEMENT.md               # Guide de lancement détaillé
```

## 🎯 Fonctionnalités Principales

### 📊 **Gestion de Base de Données Massive**
- **523 000+ enregistrements** - Performance optimisée pour gros volumes
- **Architecture PyQt5** - Interface moderne et responsive
- **Sauvegarde événementielle** - Latence sub-100ms avec EventDrivenSaveService
- **Cache intelligent** - Système de mise en cache pour performances maximales

### 📥 **Import Multi-Format Avancé**
- **Import PDF** - Extraction précise avec Camelot-Py
- **Import CSV** - Gestion intelligente des délimiteurs
- **Drag & Drop** - Multi-fichiers simultané
- **Collage intelligent** - Nettoyage automatique des extensions (.pdf, .csv)
- **Auto-complétion** - Popup filtrable pour Type et Fabricant

### 🔍 **Recherche et Filtrage Puissant**
- **Recherche temps réel** - Dans tous les champs simultanément
- **Filtres avancés** - Lignes incomplètes, doublons, catégories
- **Navigation clavier** - Flèches, Page Up/Down optimisées
- **Tri intelligent** - Multi-colonnes avec préservation des filtres

### 🔄 **Gestion des Doublons**
- **Détection visuelle** - Indicateur rouge sur le bouton Action
- **Interface hiérarchique** - Vue QTreeWidget parents/enfants
- **Exclusion DISTINCT** - Respect des décisions utilisateur
- **Fusion intelligente** - Référence principale automatique

### 🛠️ **Gestion des Pièces**
- **Double niveau** - Appareils ET pièces associées
- **Libellés descriptifs** - Champ dédié pour descriptions
- **Gestionnaire intégré** - Fenêtre dédiée avec édition temps réel
- **Validation automatique** - Vérification doublons et conflits

### 🎨 **Interface & UX Moderne**
- **Design épuré** - Interface PyQt5 moderne et intuitive
- **Colonnes configurables** - Affichage personnalisable selon les besoins
- **Raccourcis complets** - Navigation clavier optimisée (Cmd+N, Cmd+S, F5, etc.)
- **Validation temps réel** - Fenêtre dédiée avec cartes visuelles et statistiques

## 🛠️ Installation

### Dépendances
```bash
pip3 install -r requirements.txt
```

### Installation manuelle
```bash
pip3 install PyQt5
```

## ⌨️ Raccourcis Clavier

### 🚀 **Navigation & Actions**
- **Cmd+N** - Nouvelle ligne
- **Cmd+S** - Sauvegarde
- **Cmd+Z/Y** - Annuler/Refaire
- **Cmd+F** - Recherche
- **Cmd+C/V** - Copier/Coller
- **F5** - Actualiser
- **F12** - Visualiseur de logs

### 🎯 **Navigation Avancée**
- **Cmd+↑/↓** - Navigation cellules vides
- **Cmd+D** - Auto-complétion (Type/Fabricant)
- **Delete/Backspace** - Effacement cellules
- **Échap** - Réinitialiser recherche/filtres

## 📊 Performances

### 🚀 **Optimisations Majeures**
- **Requêtes SQL** : 2300ms → 150ms (93% d'amélioration)
- **Sauvegarde événementielle** : 5000ms → <100ms (98% d'amélioration)
- **Gestion 523 000+ enregistrements** avec pagination intelligente
- **Cache adaptatif** avec invalidation sélective

## 🆘 Dépannage

### Lancement de l'application
```bash
# Méthode recommandée
./1001pieces_autofill.command

# Alternative
python3 run.py
```

### Performance lente
- Vérifier la pagination (activée automatiquement pour >2000 lignes)
- Appuyer sur **Échap** pour vider filtres et recherche
- **F5** pour actualiser

---

## 📋 Changelog

Voir [CHANGELOG.md](CHANGELOG.md) pour l'historique complet des versions et nouveautés.