# Plan de Migration des Méthodes de Recherche Restantes

## 🎯 Objectif
Finaliser la migration des 3 dernières méthodes de recherche de `main_refactored.py` vers les services appropriés sans casser aucune fonctionnalité.

## 📋 État Actuel
**Branche**: `refactor/search-methods-cleanup`
**Progression**: 7 méthodes doublons déjà supprimées ✅

## 🔍 Méthodes à Migrer

### 1. `_extract_first_term(search_text: str) -> str`
**📍 Localisation actuelle**: `main_refactored.py:1211`
**🔗 Utilisations**:
- `export_service.py:114` - `self._extract_first_term(search_term)`  
- `export_service.py:144` - `self._extract_first_term(terms[0])`
- `export_service.py:165` - `self.main_window._extract_first_term(term)`

**📦 Migration cible**: `SearchService` (méthode utilitaire)
**⚠️ Impact**: Modéré - 3 appels à rediriger

### 2. `_get_current_search_term() -> str`
**📍 Localisation actuelle**: `main_refactored.py:1224`
**🔗 Utilisations**:
- `main_refactored.py:648` - `search_term = self._get_current_search_term()`
- `main_refactored.py:668` - `search_term = self._get_current_search_term()`
- `main_refactored.py:2748` - `search_term = self._get_current_search_term()`
- `main_refactored.py:2849` - `search_term = self._get_current_search_term()`
- `export_service.py:87` - `parsed_term = self._get_current_search_term()`
- `export_service.py:87` - `return self.main_window._get_current_search_term()`
- `legacy_export_service.py:94` - `search_term = self._get_current_search_term()`

**📦 Migration cible**: `AdvancedSearchService` (logique centrale de recherche)
**⚠️ Impact**: ÉLEVÉ - 7+ appels à rediriger, méthode critique

### 3. `_clear_search()`
**📍 Localisation actuelle**: `main_refactored.py:2307`
**🔗 Utilisations**:
- `main_refactored.py:2837` - `self._clear_search()`

**📦 Migration cible**: `AdvancedSearchService` 
**⚠️ Impact**: Faible - 1 seul appel

## 🗺️ Plan de Migration par Phases

### Phase 1: Migration de `_extract_first_term` 
**⏱️ Risque**: FAIBLE - Méthode simple, peu d'usages
**🔧 Étapes**:
1. Ajouter `extract_first_term()` dans `SearchService`
2. Modifier les 3 appels dans `export_service.py` vers `self.main_window.search_service.extract_first_term()`
3. Supprimer `_extract_first_term()` de `main_refactored.py`
4. Tester export CSV/HTML

### Phase 2: Migration de `_clear_search`
**⏱️ Risque**: FAIBLE - 1 seul usage
**🔧 Étapes**:
1. Ajouter `clear_search()` dans `AdvancedSearchService`
2. Modifier l'appel dans `main_refactored.py:2837` vers `self.advanced_search_service.clear_search()`
3. Supprimer `_clear_search()` de `main_refactored.py`  
4. Tester fonction "Effacer recherche"

### Phase 3: Migration de `_get_current_search_term` 
**⏱️ Risque**: ÉLEVÉ - Méthode critique très utilisée
**🔧 Étapes**:
1. Ajouter `get_current_search_term()` dans `AdvancedSearchService`
2. **ÉTAPE CRITIQUE**: Modifier les 4 appels internes dans `main_refactored.py`
3. Modifier les appels externes dans `export_service.py` et `legacy_export_service.py`
4. Supprimer `_get_current_search_term()` de `main_refactored.py`
5. **TEST COMPLET** - Vérifier toutes les fonctions de recherche et d'export

## ⚠️ Points d'Attention Critiques

### Logique de `_get_current_search_term`
Cette méthode a une logique complexe de fallback:
```python
# SOURCE DE VÉRITÉ: Le champ de recherche visible par l'utilisateur
if hasattr(self, 'search_input') and self.search_input:
    visible_term = self.search_input.text().strip()
    # + fallbacks vers TableController et AdvancedSearchService
```

**🚨 ATTENTION**: Cette logique doit être préservée exactement pour éviter les régressions.

### Dépendances Inter-Services
- `export_service.py` → `main_window._get_current_search_term()` 
- `legacy_export_service.py` → `main_window._get_current_search_term()`

**🔄 Solution**: Créer des méthodes proxy temporaires ou modifier l'injection de dépendances.

## 🧪 Plan de Tests par Phase

### Tests Phase 1 (`_extract_first_term`)
- [ ] Export CSV avec recherche simple
- [ ] Export CSV avec recherche multi-termes (||, &&)  
- [ ] Export HTML avec références multiples

### Tests Phase 2 (`_clear_search`)
- [ ] Bouton "Effacer recherche"
- [ ] Champ de recherche se vide correctement
- [ ] Tableau se recharge avec toutes les données

### Tests Phase 3 (`_get_current_search_term`)
- [ ] Recherche simple fonctionne
- [ ] Recherche avec ||, && fonctionne
- [ ] Export conserve le terme de recherche correct
- [ ] Rechargement (F5) conserve la recherche
- [ ] Ajout nouvelle ligne conserve la recherche

## 📁 Structure de Services Cible

```
src/services/
├── search_service.py
│   └── extract_first_term(search_text: str) -> str  [NOUVEAU]
└── advanced_search_service.py
    ├── get_current_search_term() -> str              [NOUVEAU]  
    └── clear_search()                                [NOUVEAU]
```

## 🔄 Méthode de Reprise

1. **Récupérer la branche**: `git checkout refactor/search-methods-cleanup`
2. **Vérifier l'état**: Les 7 doublons sont déjà supprimés ✅  
3. **Suivre les phases** dans l'ordre: 1 → 2 → 3
4. **Tester après chaque phase** avant de passer à la suivante
5. **En cas de problème**: `git reset --hard` vers le dernier commit stable

## ✅ Critères de Succès Final

- [ ] 0 méthode de recherche restante dans `main_refactored.py`
- [ ] Toutes les fonctions de recherche opérationnelles  
- [ ] Tous les exports (CSV, HTML, JSON, XML) fonctionnels
- [ ] Aucune régression détectée dans les tests manuels
- [ ] Code plus propre et mieux structuré

---
**📝 Dernière mise à jour**: 2025-09-05 - Après suppression de 7 doublons  
**🎯 Prochaine étape**: Phase 1 - Migration `_extract_first_term`