# 📚 Guide de Migration - Nouvelles Méthodes Unifiées

## 🎯 **Vue d'ensemble**

Suite à la factorisation du code d'importation, certaines méthodes ont été **dépréciées** et **remplacées** par des versions unifiées plus robustes. Ce guide vous explique comment migrer votre code.

## ⚠️ **Méthodes dépréciées**

À partir de la version **2.8.0**, les méthodes suivantes génèrent des **warnings de dépréciation** :

### 📁 **ImportManager** (src/core/import_manager.py)
```python
# ❌ DEPRECATED - Générera des warnings
_load_csv_sample_data()
_load_csv_sample_data_static() 
_load_csv_data()
_load_pdf_sample_data()
_load_pdf_sample_data_static()
_load_pdf_data()
```

### 🖥️ **MainWindow** (src/ui/main_refactored.py)
```python
# ❌ DEPRECATED - Générera des warnings
_detect_csv_columns()
_prepare_csv_sample_data()
_get_import_options_unified()
```

## ✅ **Nouvelles méthodes recommandées**

### 🔄 **Migration des méthodes CSV**

#### **Avant (deprecated)**
```python
# ❌ Ancien code avec warnings
manager = ImportManager(db_manager)
sample_data = manager._load_csv_sample_data("file.csv")
full_data = manager._load_csv_data("file.csv")
```

#### **Après (recommandé)**
```python
# ✅ Nouveau code unifié
manager = ImportManager(db_manager)
sample_data = manager.load_csv_data("file.csv", max_rows=5)
full_data = manager.load_csv_data("file.csv")  # max_rows=None par défaut
```

### 🔄 **Migration des méthodes PDF**

#### **Avant (deprecated)**
```python
# ❌ Ancien code avec warnings
manager = ImportManager(db_manager)
sample_data = manager._load_pdf_sample_data("file.pdf")
full_data = manager._load_pdf_data("file.pdf")
```

#### **Après (recommandé)**
```python
# ✅ Nouveau code unifié
manager = ImportManager(db_manager)
sample_data = manager.load_pdf_data("file.pdf", max_rows=5)
full_data = manager.load_pdf_data("file.pdf")  # max_rows=None par défaut
```

### 🔄 **Migration des méthodes d'interface**

#### **Avant (deprecated)**
```python
# ❌ Ancien code avec warnings
window = MainWindow()
columns = window._detect_csv_columns("file.csv")
sample = window._prepare_csv_sample_data("file.csv", max_lines=3)
options = window._get_import_options_unified(columns, "ref", "CSV", sample)
```

#### **Après (recommandé)**
```python
# ✅ Nouveau code avec ImportManager
manager = ImportManager(db_manager, parent_widget=window)
data = manager.load_csv_data("file.csv", max_rows=3)
columns = len(data[0]) if data else 0
results = manager.import_files(["file.csv"], show_dialog=True)
```

## 📋 **Table de correspondance complète**

| Méthode dépréciée | Nouvelle méthode | Notes |
|-------------------|------------------|-------|
| `_load_csv_sample_data(file)` | `load_csv_data(file, max_rows=5)` | Paramètre max_rows optionnel |
| `_load_csv_data(file)` | `load_csv_data(file)` | max_rows=None par défaut |
| `_load_pdf_sample_data(file)` | `load_pdf_data(file, max_rows=5)` | Paramètre max_rows optionnel |
| `_load_pdf_data(file)` | `load_pdf_data(file)` | max_rows=None par défaut |
| `_detect_csv_columns(file)` | `len(load_csv_data(file, max_rows=1)[0])` | Analyser première ligne |
| `_prepare_csv_sample_data(file, n)` | `load_csv_data(file, max_rows=n)` | Paramètre max_rows direct |
| `_get_import_options_unified(...)` | `import_files([file], show_dialog=True)` | Interface intégrée |

## 🔧 **Avantages des nouvelles méthodes**

### **1. Interface unifiée**
```python
# Une seule méthode pour tous les besoins
load_csv_data(file_path, max_rows=None)  # Échantillon OU données complètes
load_pdf_data(file_path, max_rows=None)  # Échantillon OU données complètes
```

### **2. Gestion d'erreurs améliorée**
```python
try:
    data = manager.load_csv_data("file.csv")
except ValueError as e:
    print(f"Erreur de chargement: {e}")
    # Message d'erreur explicite avec cause racine
```

### **3. Documentation complète**
```python
def load_csv_data(self, file_path: str, max_rows: Optional[int] = None) -> List[List[str]]:
    """
    Méthode unifiée pour le chargement CSV avec limite optionnelle
    
    Args:
        file_path: Chemin vers le fichier CSV
        max_rows: Nombre maximum de lignes à charger (None = toutes)
        
    Returns:
        Liste des lignes (chaque ligne est une liste de cellules)
        
    Raises:
        ValueError: Si le fichier ne peut pas être lu
    """
```

### **4. Performance optimisée**
- Détection automatique d'encodage (UTF-8, Latin-1, CP1252)
- Détection intelligente des séparateurs (`;`, `,`, `\t`)
- Gestion efficace des lignes vides
- Support des limites pour les gros fichiers

## 📅 **Planning de dépréciation**

### **Version 2.8.0 (Actuelle)**
- ✅ Nouvelles méthodes disponibles
- ⚠️ Méthodes deprecated génèrent des warnings
- ✅ Compatibilité descendante 100% préservée

### **Version 2.9.0 (Prochaine)**
- ⚠️ Warnings plus visibles dans les logs
- 📚 Documentation mise à jour
- 🔄 Migration drag&drop vers ImportManager

### **Version 3.0.0 (Future)**
- 🗑️ Suppression définitive des méthodes deprecated
- 🚀 Code 100% factorisé et optimisé

## 🛠️ **Comment migrer votre code**

### **Étape 1: Identifier les méthodes deprecated**
```bash
# Rechercher les méthodes deprecated dans votre code
grep -r "_load_csv_sample_data\|_load_pdf_sample_data\|_detect_csv_columns" your_code/
```

### **Étape 2: Remplacer progressivement**
```python
# Exemple de migration progressive
class MyImportClass:
    def __init__(self):
        self.import_manager = ImportManager(db_manager)
    
    def load_sample_data(self, file_path):
        # ❌ Ancien code
        # return self._load_csv_sample_data(file_path)
        
        # ✅ Nouveau code
        return self.import_manager.load_csv_data(file_path, max_rows=5)
```

### **Étape 3: Tester la migration**
```python
# Test de non-régression
def test_migration():
    manager = ImportManager(db_manager)
    
    # Test chargement CSV
    data = manager.load_csv_data("test.csv", max_rows=3)
    assert len(data) <= 3
    
    # Test chargement complet
    full_data = manager.load_csv_data("test.csv")
    assert len(full_data) >= len(data)
    
    print("✅ Migration réussie")
```

### **Étape 4: Supprimer les warnings**
Une fois la migration terminée, vous ne devriez plus voir de warnings du type :
```
DeprecationWarning: ImportManager._load_csv_data() est déprécié. 
Utilisez load_csv_data(file_path) à la place.
```

## 🚨 **Gestion des warnings**

### **Activer/Désactiver les warnings**
```python
import warnings

# Désactiver temporairement (non recommandé)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Afficher seulement certains warnings
warnings.filterwarnings("default", message="*ImportManager*")

# Transformer en erreur pour forcer la migration (recommandé en dev)
warnings.filterwarnings("error", category=DeprecationWarning)
```

### **Logger les warnings pour suivi**
```python
import logging
import warnings

# Rediriger les warnings vers les logs
logging.captureWarnings(True)
warnings_logger = logging.getLogger('py.warnings')
warnings_logger.setLevel(logging.WARNING)
```

## 🎯 **Bonnes pratiques**

### **1. Migrer progressivement**
- ✅ Commencer par les méthodes les plus utilisées
- ✅ Tester chaque migration individuellement
- ✅ Garder l'ancien code commenté temporairement

### **2. Utiliser les nouvelles fonctionnalités**
```python
# ✅ Profiter du paramètre max_rows pour optimiser
preview = manager.load_csv_data(large_file, max_rows=10)  # Aperçu rapide
full_data = manager.load_csv_data(large_file)  # Chargement complet si nécessaire
```

### **3. Gérer les erreurs explicitement**
```python
# ✅ Gestion d'erreurs robuste
try:
    data = manager.load_csv_data(file_path)
except ValueError as e:
    if "introuvable" in str(e):
        print("Fichier non trouvé")
    elif "invalide" in str(e):
        print("Format de fichier non supporté")
    else:
        print(f"Erreur inattendue: {e}")
```

## 🆘 **Support et questions**

### **En cas de problème**
1. Vérifiez que vous utilisez les **nouvelles signatures** de méthodes
2. Consultez les **messages de warnings** qui indiquent la méthode de remplacement
3. Testez avec des **fichiers simples** d'abord
4. Vérifiez la **documentation** intégrée avec `help(method)`

### **Migration assistée**
Les méthodes deprecated **redirigent automatiquement** vers les nouvelles méthodes, donc votre code continue de fonctionner pendant la migration.

---

**🎉 La migration vers les nouvelles méthodes unifiées vous donnera accès à un code plus robuste, mieux documenté et plus performant !**