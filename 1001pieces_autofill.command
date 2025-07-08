#!/bin/bash
# 🚀 Lanceur pour 1001pieces_autofill
# Double-cliquez sur ce fichier pour ouvrir l'application

# Aller dans le répertoire du script
cd "$(dirname "$0")"

# Vérifier que Python3 est disponible
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 n'est pas installé"
    echo "📥 Installez Python depuis https://python.org"
    read -p "Appuyez sur Entrée pour fermer..."
    exit 1
fi

# Vérifier que run.py existe
if [ ! -f "run.py" ]; then
    echo "❌ Fichier run.py introuvable"
    read -p "Appuyez sur Entrée pour fermer..."
    exit 1
fi

# Message de lancement
echo "🚀 Lancement de 1001pieces_autofill..."
echo ""

# Lancer l'application
python3 run.py

# Message de fermeture
echo ""
echo "👋 Application fermée"
read -p "Appuyez sur Entrée pour fermer ce terminal..."