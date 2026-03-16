#!/bin/bash
# 🚀 Lanceur pour 1001pieces_autofill
# Double-cliquez sur ce fichier pour ouvrir l'application avec la console

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

# Lancer l'application — console visible pour voir les logs
echo "=== 1001pieces_autofill — console de debug ==="
echo ""
python3 run.py
echo ""
echo "=== Application terminée ==="
read -p "Appuyez sur Entrée pour fermer..."
