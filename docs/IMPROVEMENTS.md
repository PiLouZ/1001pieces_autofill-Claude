# Pistes d'amélioration — 1001pieces_autofill

**Créé le** : 2026-03-11
**Principe absolu** : ZERO REGRESSION — tester après chaque modification.

Légende : ⬜ À faire · 🔄 En cours · ✅ Terminé · ⚠️ Bloqué

---

## Synthèse

| # | Catégorie | Titre | Effort | Impact | Statut |
|---|-----------|-------|--------|--------|--------|
| 1 | Perf | N+1 queries dans `pieces_count_service` | Faible | Élevé | ✅ |
| 2 | Perf | `processEvents()` dans une boucle | Faible | Élevé | ✅ |
| 3 | Perf | Recherche linéaire `find_row_by_db_id()` | Faible | Moyen | ✅ |
| 4 | Perf | `load_data()` + `count_data()` séquentiels | Moyen | Moyen | ✅ |
| 5 | Perf | Requêtes LIKE `%terme%` sans index | Élevé | Moyen | ✅ |
| 6 | Perf | Pas de virtual scrolling (fetchMore) | Élevé | Moyen | ✅ |
| 7 | UX | Message "aucun résultat" | Faible | Moyen | ✅ |
| 8 | UX | Masquer la pagination si inutile | Faible | Faible | ✅ |
| 9 | UX | Notification filtre incomplets désactivé | Faible | Faible | ✅ |
| 10 | UX | Raccourcis clavier non documentés | Faible | Faible | ✅ |

---

## Détail des améliorations

---

### 1 — N+1 queries dans `pieces_count_service` ⬜

**Catégorie** : Performance
**Effort** : Faible · **Impact** : Élevé

**Problème**
`update_pieces_count_for_rows()` itère sur chaque ligne et exécute une requête SQL séparée par ligne pour récupérer le nombre de pièces associées. Pour 1000 lignes affichées = 1000 requêtes DB.

**Fichiers concernés**
- `src/services/pieces_count_service.py` — lignes 21-36, 129-143

**Solution**
Remplacer les appels individuels par une seule requête batch :
```sql
SELECT appareil_id, COUNT(*) FROM piece_associations
WHERE appareil_id IN (id1, id2, ...)
GROUP BY appareil_id
```
Puis mapper les résultats en mémoire vers les lignes du tableau.

---

### 2 — `processEvents()` dans une boucle ⬜

**Catégorie** : Performance
**Effort** : Faible · **Impact** : Élevé

**Problème**
`_force_table_refresh()` appelle `QApplication.processEvents()` après chaque ligne mise à jour. Pour 1000 lignes = 1000 appels, ce qui génère un overhead massif et peut provoquer des re-entrées dans l'event loop.

**Fichiers concernés**
- `src/services/pieces_count_service.py` — ligne ~110

**Solution**
Déplacer le `QApplication.processEvents()` **après** la boucle, pas à l'intérieur. Si un feedback de progression est nécessaire, appeler toutes les 50-100ms via un timer ou un compteur de pas.

---

### 3 — Recherche linéaire `find_row_by_db_id()` ⬜

**Catégorie** : Performance
**Effort** : Faible · **Impact** : Moyen

**Problème**
`find_row_by_db_id()` scan toutes les lignes du tableau une par une (O(n)) pour trouver la ligne correspondant à un `db_id`. Pour 1000 lignes = jusqu'à 1000 itérations par recherche.

**Fichiers concernés**
- `src/services/pieces_count_service.py` — lignes 47-57

**Solution**
Maintenir un dict `{db_id: row_index}` mis à jour lors de chaque `load_records()`. La recherche devient O(1). Ce cache doit être invalidé à chaque rechargement de données.

---

### 4 — `load_data()` + `count_data()` séquentiels ⬜

**Catégorie** : Performance
**Effort** : Moyen · **Impact** : Moyen

**Problème**
Chaque changement de page déclenche deux requêtes DB successives : une pour charger les enregistrements, une autre pour compter le total. Ces deux opérations sont indépendantes mais bloquantes l'une après l'autre.

**Fichiers concernés**
- `src/ui/table_controller.py` — lignes ~402-403
- `src/data/database_manager.py`

**Solution**
Option A : retourner `(records, total_count)` depuis `load_data()` en une seule passe (requête + `SELECT COUNT(*)` dans la même transaction).
Option B : exécuter les deux requêtes en parallèle via deux workers.

---

### 5 — Requêtes LIKE `%terme%` sans index ✅

**Catégorie** : Performance
**Effort** : Moyen · **Impact** : Moyen

**Problème**
Toutes les recherches utilisent `LIKE "%terme%"` avec un `%` en préfixe, ce qui empêche SQLite d'utiliser les index → full table scan systématique sur 523k enregistrements.

**Fichiers concernés**
- `src/data/database_manager.py` — méthodes de construction de requêtes (~lignes 170-338)

**Complexité**
`LIKE "%terme%"` (leading wildcard) ne peut **jamais** utiliser un index B-tree en SQLite.
Une tentative de recherche optimisée (`terme%`) a déjà été désactivée (ligne 187 database_manager.py) suite à des problèmes. Passer en préfixe uniquement serait un **changement de comportement** : taper "0008" ne trouverait plus "46X0008".

**Solution recommandée** : FTS5 (Full-Text Search virtual table) — chantier significatif à planifier séparément, ou accepter le comportement actuel.

---

### 6 — Pas de virtual scrolling (fetchMore) ✅

**Catégorie** : Performance
**Effort** : Élevé · **Impact** : Moyen

**Problème**
Avec `page_size=1000`, les 1000 lignes sont toutes chargées et rendues immédiatement dans le modèle. Le scroll vers la ligne 900 peut provoquer un lag car Qt doit calculer les positions de toutes les lignes précédentes.

**Fichiers concernés**
- `src/data/appareils_table_model.py` — `load_records()` lignes ~112-120

**Solution**
Implémenter `canFetchMore()` + `fetchMore()` sur `AppareillsTableModel`. Charger les enregistrements par chunks (ex. 100 lignes) au fur et à mesure que l'utilisateur scrolle vers le bas. Réduire la `page_size` par défaut à 200-300.

---

### 7 — Message "aucun résultat" ⬜

**Catégorie** : UX
**Effort** : Faible · **Impact** : Moyen

**Problème**
Quand une recherche retourne 0 résultats, le tableau est simplement vide. L'utilisateur ne sait pas si la recherche a échoué, si le filtre est trop restrictif, ou si la base est vide.

**Fichiers concernés**
- `src/ui/table_controller.py` — `load_data()`
- `src/data/appareils_table_model.py` — `load_records()`

**Solution**
Surcharger `paint()` dans `CustomTableView` ou utiliser un widget superposé pour afficher :
*"Aucun résultat — 0 appareil trouvé pour « [terme] »"*
Visible uniquement quand `rowCount() == 0`.

---

### 8 — Masquer la pagination si inutile ⬜

**Catégorie** : UX
**Effort** : Faible · **Impact** : Faible

**Problème**
Quand `total_pages == 1`, les boutons `«` / `»` et le label de page s'affichent en grisé. Ils occupent de la place inutilement.

**Fichiers concernés**
- `src/services/navigation_service.py` — `_update_ui()` lignes ~153-171

**Solution**
Dans `_update_ui()`, masquer le widget de pagination (`setVisible(False)`) quand `total_pages <= 1`. Le réafficher dès que plusieurs pages existent.

---

### 9 — Notification filtre "incomplets" désactivé ⬜

**Catégorie** : UX
**Effort** : Faible · **Impact** : Faible

**Problème**
Quand le filtre "incomplets seulement" se désactive automatiquement (toutes les lignes ont été complétées), la vue change silencieusement. L'utilisateur peut être désorienté de voir soudainement tous les enregistrements.

**Fichiers concernés**
- `src/services/incomplete_button_service.py` — lignes ~147-152

**Solution**
Afficher un message dans la barre de statut ou un toast bref :
*"Tous les appareils sont complets — filtre désactivé"*

---

### 10 — Raccourcis clavier non documentés ⬜

**Catégorie** : UX
**Effort** : Faible · **Impact** : Faible

**Problème**
Les raccourcis clavier (Cmd+D, Cmd+F, Cmd+↑/↓, etc.) ne sont pas visibles dans l'interface. Un nouvel utilisateur ne peut pas les découvrir sans lire le code.

**Fichiers concernés**
- `src/services/navigation_service.py` — raccourcis définis mais non exposés dans l'UI

**Solution**
Option A : tooltips enrichis sur les boutons et champs de recherche ("Cmd+D : valeurs de la colonne")
Option B : panneau d'aide `?` listant tous les raccourcis disponibles

---

*Dernière mise à jour : 2026-03-11*
