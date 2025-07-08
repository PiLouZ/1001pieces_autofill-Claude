#!/bin/bash
# Script de lancement simplifié pour 1001pieces_autofill
# Double-cliquez sur ce fichier pour lancer l'application

# Aller dans le répertoire du script
cd "$(dirname "$0")"

# Lancer l'application directement
echo "🚀 Lancement de 1001pieces_autofill..."
python3 run.py

# Maintenir le terminal ouvert en cas de problème
if [ $? -ne 0 ]; then
    echo "❌ Erreur lors du lancement"
    read -p "Appuyez sur Entrée pour fermer..."
fi