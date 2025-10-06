# 🔍 Analyse des Freezes lors de l'Import de Fichiers

**Date**: 2025-10-06  
**Contexte**: Freeze du Finder lors de l'importation de fichiers  
**Objectif**: Identifier les causes et proposer des solutions architecturales

---

## 🐛 Causes Identifiées des Freezes

### 1. **Opérations Synchrones Bloquantes** ⚠️ CRITIQUE

#### Problème: `QFileDialog.exec_()` et `ImportDialog.exec_()`
**Localisation**: 
- `src/ui/main_refactored.py:1723` - `QFileDialog.getOpenFileNames()`
- `src/core/import_manager.py:756` - `dialog.exec_()`

**Impact**: Bloque le thread UI principal pendant:
- Ouverture du dialogue système (Finder doit répondre)
- Traitement de l'aperçu des fichiers PDF/CSV
- Extraction Camelot (peut prendre 5-20 secondes pour gros PDF)

```python
# ❌ PROBLÈME ACTUEL
filenames, _ = QFileDialog.getOpenFileNames(...)  # BLOQUE le thread UI
# Pendant ce temps : Finder freeze car partage des ressources système
```

---

### 2. **Chargement Immédiat des Données** ⚠️ HAUTE PRIORITÉ

#### Problème: `_get_sample_data()` appelé AVANT le dialogue
**Localisation**: `src/core/import_manager.py:739`

```python
# ❌ Chargement synchrone dans le constructeur
import_file = ImportFile(
    path=path,
    type=file_type,
    suggested_reference=self._extract_reference_from_filename(path),
    suggested_label=self._extract_reference_from_filename(path),
    data=self._get_sample_data(path, file_type)  # ⬅️ BLOQUANT ICI !
)
```

**Impact**:
- Pour 5 fichiers PDF → 5 appels synchrones à Camelot
- Chaque appel = 3-10 secondes
- Total = **15-50 secondes de freeze**

---

### 3. **Extraction PDF Synchrone (Camelot)** ⚠️ HAUTE PRIORITÉ

#### Problème: `camelot.read_pdf()` dans le thread principal
**Localisation**: `src/data/pdf_extractor_camelot.py:79-87`

```python
# ❌ Triple fallback SYNCHRONE
tables = camelot.read_pdf(str(pdf_path), flavor='stream', pages='all', edge_tol=500)
if len(tables) == 0:
    tables = camelot.read_pdf(str(pdf_path), flavor='stream', pages='all')
if len(tables) == 0:
    tables = camelot.read_pdf(str(pdf_path), flavor='lattice', pages='all')
```

**Impact**:
- Chaque tentative = 3-7 secondes
- Avec fallbacks = 9-21 secondes par fichier
- CPU-intensif (analyse image + OCR)

---

### 4. **Multiples `QApplication.processEvents()`** ⚠️ MOYENNE PRIORITÉ

#### Problème: Appels dispersés mais inefficaces
**Localisation**:
- `src/ui/file_processing_service.py:165, 175, 288`
- `src/ui/main_refactored.py:2373, 2728`

**Impact**: 
- Ne débloque PAS réellement le thread
- Donne illusion de réactivité mais freeze persiste
- Peut causer des comportements imprévisibles

---

### 5. **Absence de Feedback Visuel Pendant le Chargement** ⚠️ UX

#### Problème: Aucun spinner/progress pendant `_get_sample_data()`
**Impact**: Utilisateur pense que l'app est plantée

---

## 🎯 Pistes d'Amélioration Architecturales

### 📦 PISTE 1: Architecture Asynchrone avec QThread

#### Objectif: Déplacer TOUTES les opérations I/O hors du thread UI

**Architecture Proposée**:
```
UI Thread (MainWindow)
    ↓
Worker Thread (ImportWorker)
    ↓
    ├─ Extraction PDF (Camelot)
    ├─ Lecture CSV
    └─ Aperçu données
    ↓
Signal → UI Thread (Mise à jour interface)
```

**Avantages**:
- ✅ UI toujours responsive
- ✅ Finder ne freeze plus
- ✅ Annulation possible à tout moment
- ✅ Progress bar en temps réel

**Fichiers à modifier**:
- `src/services/async_import_worker.py` (NOUVEAU)
- `src/core/import_manager.py` (refactoriser)
- `src/ui/main_refactored.py` (connecter signaux)

**Effort**: 🔴 Élevé (2-3 jours)

---

### 📦 PISTE 2: Chargement Lazy des Aperçus

#### Objectif: Charger les aperçus APRÈS ouverture du dialogue

**Principe**:
```python
# ✅ AMÉLIORATION
import_file = ImportFile(
    path=path,
    type=file_type,
    suggested_reference=self._extract_reference_from_filename(path),
    data=None  # ⬅️ PAS DE DONNÉES AU DÉBUT
)

# Plus tard, dans le dialogue (en arrière-plan):
QTimer.singleShot(100, lambda: self._load_preview_async(import_file))
```

**Avantages**:
- ✅ Dialogue s'ouvre IMMÉDIATEMENT
- ✅ Aperçu se charge en arrière-plan
- ✅ Feedback visuel pendant le chargement

**Fichiers à modifier**:
- `src/core/import_manager.py:736-741`
- `src/core/import_manager.py:420-539` (ImportDialog)

**Effort**: 🟡 Moyen (1 jour)

---

### 📦 PISTE 3: Cache des Métadonnées Fichiers

#### Objectif: Ne pas recharger les mêmes fichiers

**Principe**:
```python
# Cache simple basé sur (path, mtime)
_file_metadata_cache = {}

def _get_sample_data_cached(path, file_type):
    mtime = os.path.getmtime(path)
    cache_key = (path, mtime)
    
    if cache_key in _file_metadata_cache:
        return _file_metadata_cache[cache_key]
    
    data = _load_sample_data_real(path, file_type)
    _file_metadata_cache[cache_key] = data
    return data
```

**Avantages**:
- ✅ Réimport instantané si fichier déjà vu
- ✅ Pas de re-extraction Camelot
- ✅ Mémoire contrôlée (LRU cache)

**Fichiers à modifier**:
- `src/core/import_manager.py` (ajouter cache)
- `src/data/pdf_extractor_camelot.py` (ajouter cache)

**Effort**: 🟢 Faible (2-3 heures)

---

### 📦 PISTE 4: Aperçu Minimaliste (Première Page Seulement)

#### Objectif: Charger uniquement la 1ère page pour l'aperçu

**Principe**:
```python
# ❌ ACTUEL : Charge TOUTES les pages
tables = camelot.read_pdf(str(pdf_path), flavor='stream', pages='all')

# ✅ AMÉLIORATION : Seulement page 1 pour aperçu
tables = camelot.read_pdf(str(pdf_path), flavor='stream', pages='1')
```

**Avantages**:
- ✅ 10x plus rapide (1 page vs 50 pages)
- ✅ Aperçu suffit pour validation
- ✅ Extraction complète seulement après validation

**Fichiers à modifier**:
- `src/data/pdf_extractor_camelot.py:79`
- `src/core/import_manager.py:522` (méthode load_pdf_data)

**Effort**: 🟢 Très faible (30 minutes)

---

### 📦 PISTE 5: Drag & Drop Non-Bloquant

#### Objectif: Remplacer `exec_()` par `show()` + callbacks

**Principe**:
```python
# ❌ ACTUEL : Bloquant
if dialog.exec_() == QDialog.Accepted:
    config = dialog.get_configuration()

# ✅ AMÉLIORATION : Non-bloquant
dialog.accepted.connect(lambda: self._on_import_accepted(dialog))
dialog.rejected.connect(lambda: self._on_import_cancelled())
dialog.show()  # Retourne immédiatement
```

**Avantages**:
- ✅ Finder reste responsive
- ✅ Utilisateur peut annuler à tout moment
- ✅ Meilleure UX

**Fichiers à modifier**:
- `src/core/import_manager.py:754-761`
- `src/ui/main_refactored.py:2420`

**Effort**: 🟡 Moyen (4-5 heures)

---

### 📦 PISTE 6: Progress Bar Avant Ouverture Dialogue

#### Objectif: Feedback visuel IMMÉDIAT

**Principe**:
```python
# Afficher spinner immédiatement
progress = QProgressDialog("Analyse des fichiers...", "Annuler", 0, len(files))
progress.setWindowModality(Qt.WindowModal)
progress.show()

# Charger en arrière-plan
worker = FileAnalysisWorker(files)
worker.progress.connect(progress.setValue)
worker.finished.connect(lambda: self._show_import_dialog(worker.results))
worker.start()
```

**Avantages**:
- ✅ Utilisateur sait que l'app travaille
- ✅ Possibilité d'annuler
- ✅ Meilleure perception de performance

**Fichiers à modifier**:
- `src/core/import_manager.py:716-764`

**Effort**: 🟢 Faible (1-2 heures)

---

## 📊 Comparaison des Pistes

| Piste | Effort | Impact | Compatibilité | Priorité |
|-------|--------|--------|---------------|----------|
| **1. QThread Async** | 🔴 Élevé | 🟢 Très élevé | ⚠️ Refactoring majeur | 🥇 **HAUTE** |
| **2. Lazy Loading** | 🟡 Moyen | 🟢 Élevé | ✅ Compatible | 🥇 **HAUTE** |
| **3. Cache Métadonnées** | 🟢 Faible | 🟡 Moyen | ✅ Compatible | 🥉 Moyenne |
| **4. Aperçu 1ère Page** | 🟢 Très faible | 🟢 Élevé | ✅ Compatible | 🥇 **HAUTE** |
| **5. Dialog Non-Bloquant** | 🟡 Moyen | 🟢 Élevé | ⚠️ Changement patterns | 🥈 Moyenne |
| **6. Progress Bar** | 🟢 Faible | 🟡 Moyen (UX) | ✅ Compatible | 🥉 Moyenne |

---

## 🚀 Plan d'Action Recommandé

### Phase 1 : Quick Wins (1 jour)
1. ✅ **Piste 4** : Aperçu 1ère page seulement (30 min)
2. ✅ **Piste 3** : Cache métadonnées (2-3h)
3. ✅ **Piste 6** : Progress bar immédiate (1-2h)

**Gain estimé** : 70% réduction du freeze

---

### Phase 2 : Optimisations Structurelles (2 jours)
1. ✅ **Piste 2** : Lazy loading aperçus (1 jour)
2. ✅ **Piste 5** : Dialogue non-bloquant (4-5h)

**Gain estimé** : 90% réduction du freeze

---

### Phase 3 : Architecture Complète (3 jours)
1. ✅ **Piste 1** : QThread Worker complet (2-3 jours)

**Gain estimé** : 100% élimination des freezes

---

## 🔬 Détails Techniques Supplémentaires

### Problème Spécifique: Finder Freeze

**Hypothèse**: Contention des ressources système entre Qt et Finder
- `QFileDialog` utilise les APIs Finder natifs (FSEvents, FSCatalog)
- Camelot charge des fichiers volumineux (mmap, file descriptors)
- Conflit sur les locks système de fichiers

**Solution**: Libérer les ressources AVANT d'ouvrir les dialogues

---

### Pattern Actuel vs Pattern Idéal

```
❌ ACTUEL (Synchrone - Bloquant):
User drops file
    → dropEvent() [UI Thread]
        → import_files() [UI Thread]
            → _get_sample_data() [UI Thread]
                → camelot.read_pdf() [UI Thread] ⬅️ FREEZE 10s
            → dialog.exec_() [UI Thread] ⬅️ BLOQUE
                → Validation
            → _execute_import() [UI Thread]
        → table.load_data()

✅ IDÉAL (Asynchrone - Non-Bloquant):
User drops file
    → dropEvent() [UI Thread]
        → show_progress() [UI Thread]
        → ImportWorker.start() [Worker Thread]
            → _get_sample_data() [Worker Thread] ⬅️ PAS DE FREEZE
                → camelot.read_pdf() [Worker Thread]
            → Signal: data_ready
        → dialog.show() [UI Thread] ⬅️ NON-BLOQUANT
            → user validates
            → Signal: accepted
        → ImportWorker.execute() [Worker Thread]
            → Signal: progress
        → Signal: completed
        → table.load_data() [UI Thread]
```

---

## 📝 Conclusion

**Problème racine** : Architecture synchrone dans le thread UI  
**Solution court terme** : Pistes 3, 4, 6 (1 jour)  
**Solution long terme** : Architecture asynchrone complète (3 jours)

**ROI recommandé** :
- Commencer par Phase 1 (Quick Wins)
- Mesurer l'amélioration
- Décider si Phase 2-3 nécessaires
