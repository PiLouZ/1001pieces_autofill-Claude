# 🚀 Guide de Lancement - 1001pieces_autofill

## 🎯 Méthodes de Lancement Recommandées

### 1. **🖱️ Lancement Sans Terminal (Recommandé)**
```bash
python3 launch_app.py
```
**Avantages :**
- ✅ Aucun terminal visible
- ✅ Interface plus propre
- ✅ Fermeture automatique du terminal
- ✅ Expérience utilisateur optimale

### 2. **⌨️ Lancement Classique avec Vérifications**
```bash
python3 run.py
```
**Avantages :**
- ✅ Vérifications de dépendances
- ✅ Messages d'erreur détaillés
- ✅ Migration automatique de la base
- ✅ Terminal visible pour debugging

### 3. **🔗 Lancement Direct (Développeurs)**
```bash
python3 -m src.ui.main_refactored
```
**Avantages :**
- ✅ Démarrage le plus rapide
- ✅ Aucune vérification préalable
- ✅ Accès direct à l'application

## 🛠️ Prérequis

### Installation des Dépendances
```bash
# Méthode recommandée
pip3 install -r requirements.txt

# Installation manuelle
pip3 install PyQt5
```

### Vérification de l'Installation
```bash
python3 -c "import PyQt5; print('PyQt5 installé avec succès')"
```

## 📁 Structure des Fichiers de Lancement

```
📦 Lanceurs disponibles/
├── 🚀 launch_app.py           # Nouveau - Sans terminal
├── 🚀 run.py                  # Classique - Avec vérifications
├── 🚀 Lancer_1001pieces.command # Ancien - Compatible macOS
└── 📂 src/ui/main_refactored.py # Direct - Pour développeurs
```

## 🔧 Personnalisation du Lancement

### Variables d'Environnement Supportées
```bash
# Niveau de logging
export LOG_LEVEL=DEBUG    # DEBUG, INFO, WARNING, ERROR

# Répertoire de logs personnalisé
export LOG_DIR=/path/to/logs

# Taille de page par défaut
export DEFAULT_PAGE_SIZE=2000

# Lancement
python3 launch_app.py
```

### Options de Ligne de Commande
```bash
# Lancement avec options spécifiques
python3 run.py --debug          # Mode debug
python3 run.py --no-migration   # Sans migration auto
python3 run.py --page-size 500  # Taille de page personnalisée
```

## 🆘 Résolution de Problèmes

### ❌ "Terminal s'ouvre toujours"
**Solution :**
```bash
# Utiliser le nouveau lanceur
python3 launch_app.py

# Alternative : Créer un alias
echo "alias app1001='python3 $(pwd)/launch_app.py'" >> ~/.zshrc
source ~/.zshrc
app1001
```

### ❌ "ModuleNotFoundError: No module named 'PyQt5'"
**Solution :**
```bash
# Installer PyQt5
pip3 install PyQt5

# Vérifier l'installation
python3 -c "import PyQt5; print('✅ PyQt5 OK')"
```

### ❌ "Permission denied"
**Solution :**
```bash
# Rendre les scripts exécutables
chmod +x launch_app.py
chmod +x run.py
chmod +x Lancer_1001pieces.command
```

### ❌ "Database locked"
**Solution :**
```bash
# Vérifier qu'aucune autre instance n'est ouverte
ps aux | grep main_refactored

# Si nécessaire, tuer les processus
killall python3
```

## 📱 Intégration Système

### 🍎 macOS - Création d'un Alias Bureau
```bash
# Créer un alias sur le bureau
ln -s "$(pwd)/launch_app.py" ~/Desktop/"1001pieces App"

# Ou créer un script .command
echo '#!/bin/bash
cd "$(dirname "$0")"
python3 launch_app.py' > ~/Desktop/1001pieces.command
chmod +x ~/Desktop/1001pieces.command
```

### 🐧 Linux - Création d'un .desktop
```bash
cat > ~/.local/share/applications/1001pieces.desktop << EOF
[Desktop Entry]
Name=1001pieces Autofill
Comment=Gestionnaire d'appareils
Exec=python3 $(pwd)/launch_app.py
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=Office;
EOF
```

### 🪟 Windows - Création d'un raccourci
```batch
# Créer un fichier .bat
echo @echo off > 1001pieces.bat
echo cd /d "%~dp0" >> 1001pieces.bat
echo python launch_app.py >> 1001pieces.bat
```

## 🚀 Optimisation des Performances

### Configuration pour Gros Volumes (83k+ lignes)
```bash
# Variables d'environnement optimisées
export DEFAULT_PAGE_SIZE=1000
export MAX_DISPLAY_ROWS=2000
export SEARCH_LIMIT=5000

# Lancement optimisé
python3 launch_app.py
```

### Configuration pour Machines Lentes
```bash
# Variables d'environnement conservatrices
export DEFAULT_PAGE_SIZE=500
export MAX_DISPLAY_ROWS=1000
export AUTO_SAVE_INTERVAL=10000

# Lancement
python3 launch_app.py
```

## 📊 Monitoring du Lancement

### Vérification du Bon Fonctionnement
```bash
# Vérifier les logs de démarrage
tail -f logs/detailed.log

# Vérifier les processus
ps aux | grep -E "(python|1001pieces)"

# Vérifier les ports (si applicable)
netstat -an | grep LISTEN
```

### Métriques de Performance
```bash
# Temps de démarrage (doit être < 3 secondes)
time python3 launch_app.py

# Utilisation mémoire
ps -o pid,ppid,%mem,command -p $(pgrep -f main_refactored)
```

---

## ✅ Checklist de Lancement Réussi

- [ ] **PyQt5 installé** (`python3 -c "import PyQt5"`)
- [ ] **Permissions correctes** (`ls -la launch_app.py`)
- [ ] **Base de données accessible** (`ls -la data/appareils.db`)
- [ ] **Logs créés** (`ls -la logs/`)
- [ ] **Interface s'ouvre** (fenêtre principale visible)
- [ ] **Données chargées** (tableau non vide)

**🎉 Si tous les points sont verts, l'application est prête à l'emploi !**

---

**📝 Note :** Ce guide couvre toutes les méthodes de lancement. Pour un usage quotidien, recommandation : `python3 launch_app.py`