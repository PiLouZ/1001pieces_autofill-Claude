#!/bin/bash
# Script de lancement pour l'application de gestion d'appareils
# Double-cliquez sur ce fichier pour lancer l'application

# Aller dans le répertoire racine de l'application
cd "$(dirname "$0")"

# Afficher le répertoire courant
echo "📁 Répertoire: $(pwd)"
echo "🚀 Lancement de l'application de gestion d'appareils..."
echo ""

# Vérifier que Python3 est disponible
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 n'est pas installé ou non trouvé dans le PATH"
    echo "Veuillez installer Python3 depuis https://python.org"
    read -p "Appuyez sur Entrée pour fermer..."
    exit 1
fi

# Vérifier que PyQt5 est installé
python3 -c "import PyQt5" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  PyQt5 n'est pas installé. Installation..."
    python3 -m pip install PyQt5
    if [ $? -ne 0 ]; then
        echo "❌ Échec de l'installation de PyQt5"
        read -p "Appuyez sur Entrée pour fermer..."
        exit 1
    fi
    echo "✅ PyQt5 installé avec succès"
fi

# Vérifier que l'application existe
if [ ! -f "run.py" ]; then
    echo "❌ Fichier run.py introuvable"
    echo "Assurez-vous que le script est dans le bon répertoire"
    read -p "Appuyez sur Entrée pour fermer..."
    exit 1
fi

# Lancer l'application avec run.py (plus robuste)
echo "🎯 Lancement de l'application..."
python3 run.py

# Si on arrive ici, l'application s'est fermée normalement
echo "👋 Application fermée"