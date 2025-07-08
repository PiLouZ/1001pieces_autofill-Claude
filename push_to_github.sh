#!/bin/bash

# 🚀 Script automatisé pour pousser vers GitHub
# Usage: ./push_to_github.sh

echo "🎉 Préparation pour GitHub - 1001pieces_autofill v2.0.0"
echo "=================================================="

# Vérifier qu'on est dans le bon répertoire
if [ ! -f "launch_app.py" ]; then
    echo "❌ Erreur: Veuillez exécuter ce script depuis le répertoire du projet"
    exit 1
fi

# Initialiser git si nécessaire
if [ ! -d ".git" ]; then
    echo "📁 Initialisation du repository git..."
    git init
fi

# Ajouter tous les fichiers
echo "📋 Ajout des fichiers au staging..."
git add .

# Créer le commit avec message descriptif
echo "💾 Création du commit..."
git commit -m "🎉 Version 2.0.0 - Application moderne et interactive

✨ Nouvelles fonctionnalités:
- 🔍 Validation et Incohérences interactive
- ⚙️ Gestion des colonnes configurables  
- 📊 Performance optimisée (83k+ records)
- 🎨 Interface Bootstrap moderne
- 🚀 Lancement sans terminal

🔧 Améliorations techniques:
- Pagination intelligente
- Raccourcis clavier avancés
- Logs structurés
- Documentation complète

🎯 Prêt pour production

🤝 Développé par Claude (Anthropic) en collaboration avec l'utilisateur"

# Configurer le remote GitHub
echo "🔗 Configuration du repository distant..."
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/PiLouZ/1001pieces_autofill-Claude.git

# Configurer la branche principale
echo "🌿 Configuration de la branche main..."
git branch -M main

# Pousser vers GitHub
echo "🚀 Push vers GitHub..."
echo "⚠️  Vous devrez peut-être entrer vos identifiants GitHub..."
git push -u origin main

# Vérification finale
if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 ✅ SUCCESS! Projet publié sur GitHub"
    echo "🔗 Votre repository: https://github.com/PiLouZ/1001pieces_autofill-Claude"
    echo ""
    echo "📋 Actions recommandées sur GitHub:"
    echo "- Vérifier que le README.md s'affiche correctement"
    echo "- Créer une release v2.0.0 si souhaité"
    echo "- Configurer les topics/tags pour la visibilité"
else
    echo ""
    echo "❌ Erreur lors du push"
    echo "💡 Solutions possibles:"
    echo "- Vérifier vos identifiants GitHub"
    echo "- Utiliser un token d'accès personnel"
    echo "- Vérifier que le repository existe sur GitHub"
fi