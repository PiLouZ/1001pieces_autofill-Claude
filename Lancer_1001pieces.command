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
if [ ! -f "launch_app.py" ]; then
    echo "❌ Fichier launch_app.py introuvable"
    echo "Assurez-vous que le script est dans le bon répertoire"
    read -p "Appuyez sur Entrée pour fermer..."
    exit 1
fi

# Lancer l'application sans terminal (méthode moderne)
echo "🎯 Lancement de l'application (sans terminal)..."
echo "✨ Le terminal va se fermer automatiquement..."

# Utiliser nohup pour détacher le processus du terminal et fermer automatiquement
nohup python3 launch_app.py > /dev/null 2>&1 &

# Attendre un instant pour s'assurer que l'application démarre
sleep 2

# Fermer automatiquement ce terminal en arrière-plan
osascript -e 'tell application "Terminal" to close (every window whose name contains "Lancer_1001pieces.command")' > /dev/null 2>&1 &

# Fermer immédiatement ce script
exit 0