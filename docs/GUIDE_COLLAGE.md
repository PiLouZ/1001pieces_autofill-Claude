# 📋 Guide de Collage de Données

## 🎯 Fonctionnalité restaurée !

La fonctionnalité de **collage de données depuis le presse-papiers** a été implémentée dans la version refactorisée.

## 🚀 Comment utiliser le collage

### 1. **Préparer les données**
- Copiez des données depuis Excel, Numbers, ou tout tableur
- Format attendu : colonnes séparées par des tabulations
- Lignes séparées par des retours à la ligne

### 2. **Coller dans l'application**
Plusieurs méthodes :
- **Ctrl+V** (Cmd+V sur Mac)
- **Bouton "📥 Coller"** dans la barre d'outils
- **Menu contextuel** (clic droit)

### 3. **Configuration du collage**
L'application vous demandera :
- **Référence de pièce** (optionnel) - sera associée à tous les appareils
- **Catégorie** (optionnel) - sera appliquée à tous les appareils

### 4. **Validation automatique**
- Les données sont validées avant insertion
- En cas d'erreur, vous pouvez choisir de continuer ou arrêter
- Un résumé s'affiche à la fin

## 📊 Formats de données supportés

### 🔢 **Règles de mapping selon le nombre de colonnes**

#### **4+ colonnes** → Insertion à partir de la colonne A
```
Type        Fabricant    Ref_Modele    Ref_Commercial    Autre_Ref    Catégorie    Notes
Lave-linge  Bosch       WAG24260FF    12345             ABC-123      Électro      Test
Frigo       Samsung     RB34T602FSA   67890             DEF-456      Électro      ...
```
**Mapping :** A=Type, B=Fabricant, C=Ref_Modele, D=Ref_Commercial, E=Autre_Ref, F=Catégorie, G=Notes

#### **2-3 colonnes** → Insertion à partir de la colonne C (avec auto-completion)
```
WAG24260FF    12345             ABC-123
RB34T602FSA   67890             DEF-456
```
**Mapping :** C=Ref_Modele, D=Ref_Commercial, E=Autre_Ref  
**Auto-completion :** Type et Fabricant complétés automatiquement si trouvés en base

#### **1 colonne ou 5+ colonnes non standard** → Ligne ignorée
- Message d'erreur affiché
- Ligne sautée automatiquement

## ✨ Fonctionnalités

### ✅ **Validation en temps réel**
- Contrôle des formats de référence
- Vérification des doublons
- Validation des longueurs de champs

### ✅ **Association automatique**
- Référence de pièce commune pour tout le lot
- Catégorie appliquée à tous les appareils
- Timestamps automatiques

### ✅ **Auto-completion intelligente**
- Pour les collages 2-3 colonnes (références seulement)
- Recherche Type et Fabricant dans la base existante
- Basée sur la correspondance des références (exacte ou partielle)
- Complète uniquement les champs vides

### ✅ **Gestion d'erreurs**
- Messages d'erreur clairs
- Possibilité de continuer malgré les erreurs
- Rollback en cas de problème grave

### ✅ **Retour visuel**
- Barre de statut mise à jour
- Dialogue de confirmation
- Compteur d'éléments ajoutés

## 🔧 Raccourcis clavier

| Raccourci | Action |
|-----------|--------|
| **Ctrl+V** | Coller depuis le presse-papiers |
| **Ctrl+C** | Copier la sélection |
| **Ctrl+N** | Nouvelle ligne vide |
| **Ctrl+S** | Sauvegarder |
| **F5** | Actualiser |

## 💡 Conseils d'utilisation

### 📝 **Préparation des données**
1. Organisez vos données dans l'ordre des colonnes
2. Évitez les cellules fusionnées
3. Utilisez des formats simples (texte)

### 🎯 **Optimisation**
1. Groupez les appareils par catégorie pour le collage
2. Préparez les références de pièces à l'avance
3. Vérifiez les doublons avant collage

### ⚠️ **Attention**
- Les données sont ajoutées, pas remplacées
- La validation peut rejeter certaines lignes
- Utilisez Ctrl+Z pour annuler si nécessaire

## 🆘 En cas de problème

### "Aucune donnée dans le presse-papiers"
- Vérifiez que vous avez bien copié des données
- Assurez-vous que le format est texte/tableur

### "Données invalides"
- Vérifiez les formats de référence (pas de caractères spéciaux)
- Contrôlez les longueurs de champs
- Éliminez les doublons de référence

### "Erreur lors du collage"
- Vérifiez la connexion à la base de données
- Redémarrez l'application si nécessaire
- Consultez les messages d'erreur détaillés

---

🎉 **La fonctionnalité de collage est maintenant pleinement opérationnelle !**