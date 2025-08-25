# Nouveaux Workflows d'Importation

## Vue d'ensemble

Le nouveau système d'importation basé sur `ImportManager` introduit une approche unifiée et flexible pour importer des fichiers CSV et PDF avec support des **libellés hiérarchiques**.

## 🎯 Fonctionnalités Principales

### ✨ Import Multi-Fichiers avec Libellés Hiérarchiques

**Concept :** Chaque appareil peut être associé à **plusieurs références de pièces** :
- Une **référence commune** (optionnelle) pour tous les fichiers
- Une **référence individuelle** basée sur le nom de chaque fichier

### 📁 Types d'Import Supportés

1. **Import Simple** (1 fichier) - Compatible avec l'ancien système
2. **Import Multi-Fichiers** (2+ fichiers) - Nouvelle fonctionnalité

---

## 🚀 Workflows Détaillés

### 1. Import Simple (1 fichier)

**Utilisation :** Menu → Importer → Sélectionner un fichier

**Comportement :**
- Interface simplifiée (comme avant)
- Référence de pièce = nom du fichier
- Libellé personnalisable

**Exemple :**
```
Fichier: resistance_chauffante.csv
Référence créée: "resistance_chauffante"
Libellé: "resistance_chauffante" (personnalisable)
```

### 2. Import Multi-Fichiers (2+ fichiers)

**Utilisation :** Menu → Importer → Sélectionner plusieurs fichiers

**Interface de Configuration :**

#### Section 1: Référence Commune (Optionnelle)
```
☑ Associer une référence commune à tous les fichiers
📝 Référence: LOT_2024_001
```

#### Section 2: Gestion des Libellés
```
☑ Utiliser un libellé commun pour toutes les pièces
📝 Libellé commun: "Pièces détachées lave-vaisselle Bosch"

Libellés individuels par fichier:
📄 resistance_chauffante.pdf → "resistance_chauffante"
📄 joint_porte.csv → "joint_porte"
📄 pompe_vidange.pdf → "pompe_vidange"
```

**Résultat pour chaque appareil :**
- ✅ Associé à `"LOT_2024_001"` (référence commune)
- ✅ Associé à `"resistance_chauffante"` (référence individuelle)

---

## 🎨 Interface Utilisateur

### Dialogue Unifié d'Import

```
┌─────────────────────────────────────────┐
│ Configuration d'importation             │
├─────────────────────────────────────────┤
│ 📁 3 fichiers:                         │
│   • resistance_chauffante.pdf          │
│   • joint_porte.csv                    │
│   • pompe_vidange.pdf                  │
├─────────────────────────────────────────┤
│ ☑ Référence commune: LOT_LAVE_2024     │
├─────────────────────────────────────────┤
│ ☑ Libellé commun: Pièces lave-vaisselle│
│                                         │
│ Libellés individuels:                   │
│ 📄 resistance_chauffante.pdf: [____]   │
│ 📄 joint_porte.csv: [____]             │
│ 📄 pompe_vidange.pdf: [____]           │
├─────────────────────────────────────────┤
│ === Aperçu des données ===             │
│ Type | Fabricant | Ref...              │
│ Résistance | Bosch | 12345...          │
├─────────────────────────────────────────┤
│            [Annuler] [Importer]         │
└─────────────────────────────────────────┘
```

### Messages de Résultats Améliorés

```
🎉 Import terminé avec succès !

📊 Résumé:
• 3/3 fichier(s) traité(s) (import multi-fichiers)
• 45 lignes importées
• 12 nouveaux appareils créés
• 33 appareils existants trouvés  
• 90 associations pièces-appareils créées
```

---

## 🔄 Drag & Drop Amélioré

### Nouveau Comportement
- **Plusieurs fichiers simultanés** : Glisser 5 fichiers → Interface de configuration
- **Mélange CSV/PDF** : `piece.csv` + `joint.pdf` → Traitement unifié
- **Configuration automatique** : Dialogue s'affiche pour plus d'1 fichier

### Ancien vs Nouveau

| Aspect | Ancien | Nouveau |
|--------|--------|---------|
| Fichiers | 1 seul | Multiple |
| Types | CSV ou PDF | CSV + PDF mélangés |
| Interface | Automatique | Configurable |
| Résultat | 1 association/appareil | Multiple associations |

---

## 🧪 Compatibilité

### Méthodes Préservées
- `_import_file_legacy()` - Ancienne logique complète
- `dropEvent_legacy()` - Ancien drag & drop
- `_import_csv_from_path()` - Import CSV direct
- `_import_pdf_from_path()` - Import PDF direct

### Migration Progressive
```python
# Nouveau (recommandé)
results = self.import_manager.import_files(file_paths, show_dialog=True)

# Ancien (encore supporté)
self._import_file_legacy()
```

---

## 📋 Cas d'Usage Concrets

### Cas 1: Import de Lot de Pièces
```
Situation: 5 PDF de pièces détachées d'un même modèle
Configuration:
- Référence commune: "LOT_LAVE_BOSCH_2024"
- Libellé commun: "Pièces détachées lave-vaisselle Bosch WAK28267FF"
- Libellés individuels: noms des fichiers

Résultat: Chaque appareil associé à 2 références (lot + pièce)
```

### Cas 2: Import Mixte CSV/PDF
```
Situation: 2 CSV techniques + 3 PDF catalogues
Configuration:
- Pas de référence commune
- Libellé commun: "Import catalogue mars 2024"
- Libellés individuels: personnalisés

Résultat: Association flexible selon les besoins
```

### Cas 3: Import Simple (Rétrocompatible)
```
Situation: 1 fichier CSV comme avant
Configuration: Interface simplifiée automatique
Résultat: Comportement identique à l'ancien système
```

---

## 🔧 Configuration Avancée

### Options Techniques
```python
config = ImportConfiguration(
    files=[...],
    import_type=ImportType.MULTI_FILE,
    use_common_reference=True,
    common_reference="LOT_2024_001",
    label_config=LabelConfiguration(
        use_common_label=True,
        common_label="Pièces détachées",
        individual_labels={
            "/path/file1.csv": "Résistance",
            "/path/file2.pdf": "Joint"
        }
    )
)
```

### API Simplifiée
```python
# Import avec dialogue
from src.core.import_manager import import_files_with_dialog
results = import_files_with_dialog(file_paths, db_manager, parent)

# Import programmatique
manager = ImportManager(db_manager, parent)
results = manager.import_files(file_paths, show_dialog=False)
```

---

## 🎯 Avantages

### Pour l'Utilisateur
- ✅ **Multi-fichiers en une fois** : Plus d'efficacité
- ✅ **Organisation flexible** : Références multiples par appareil
- ✅ **Interface cohérente** : Même dialogue pour tout
- ✅ **Aperçu des données** : Validation avant import

### Pour le Développeur
- ✅ **Code factorisé** : Plus de duplication CSV/PDF
- ✅ **Architecture testable** : Tests automatisés
- ✅ **Extensible** : Ajout facile de nouveaux formats
- ✅ **Rétrocompatible** : Migration sans risque

---

## 🚀 Utilisation Recommandée

1. **Import quotidien** : Utiliser le nouveau système par défaut
2. **Import de lots** : Exploiter les libellés hiérarchiques
3. **Debugging** : Utiliser les méthodes `_legacy` si nécessaire
4. **Développement** : Étendre `ImportManager` pour nouveaux besoins

Le nouveau système est **100% rétrocompatible** tout en offrant des **fonctionnalités avancées** pour une meilleure organisation des données.