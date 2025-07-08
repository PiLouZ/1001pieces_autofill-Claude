# Architecture Robuste pour le Tri des Colonnes

## Problèmes identifiés dans l'ancienne architecture

### 1. Mapping fragile UI/DB
- Les index de colonnes étaient mappés de façon statique
- Le tri cassait la correspondance entre l'affichage et la base de données
- La colonne "Nb Pièces" injectée à l'index 5 perturbait tout le mapping

### 2. Perte de cohérence lors des opérations
- Les opérations (duplication, complétion) utilisaient des index UI incorrects après tri
- Les modifications étaient appliquées aux mauvaises colonnes
- Pas de vérification de l'intégrité des données

### 3. Absence de tri stable
- Pas de clé secondaire pour garantir un ordre reproductible
- Les IDs de base de données n'étaient pas préservés comme référence

## Nouvelle architecture

### Vue d'ensemble

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MainWindow    │───▶│ TableSortManager│───▶│TableDataManager│
│                 │    │                 │    │                 │
│ - Interface UI  │    │ - Gestion tri   │    │ - Mapping robust│
│ - Événements    │    │ - Signaux Qt    │    │ - Données format│
│ - Actions user  │    │ - Sélections    │    │ - Intégrité     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                        │
                                │                        ▼
                                │               ┌─────────────────┐
                                │               │ DatabaseManager │
                                │               │                 │
                                └───────────────▶ - Requêtes SQL │
                                                │ - Transactions  │
                                                │ - Validation    │
                                                └─────────────────┘
```

### Composants principaux

#### 1. TableDataManager
**Responsabilité** : Gestionnaire centralisé des données du tableau

**Fonctionnalités clés** :
- Mapping robuste entre colonnes UI et champs DB
- Gestion des colonnes calculées (Nb Pièces)
- Tri stable avec clé secondaire (ID)
- Préservation de l'intégrité des données

**Mapping des colonnes** :
```python
{
    0: TableColumn("Type", "type", 0, 0, False, True, True),
    1: TableColumn("Fabricant", "manufacturer", 1, 1, False, True, True),
    2: TableColumn("Référence Modèle", "ref_modele", 2, 2, False, True, True),
    3: TableColumn("Référence Commerciale", "commercial_ref", 3, 3, False, True, True),
    4: TableColumn("Autre Référence", "other_ref", 4, 4, False, True, True),
    5: TableColumn("Nb Pièces", "pieces_count", 5, -1, True, True, False),  # Calculée
    6: TableColumn("Catégorie", "category", 6, 5, False, True, True),
    7: TableColumn("Notes", "notes", 7, 6, False, True, True)
}
```

#### 2. TableSortManager
**Responsabilité** : Coordination du tri avec Qt et préservation des sélections

**Fonctionnalités clés** :
- Désactivation du tri automatique Qt
- Gestion personnalisée des clics sur en-têtes
- Préservation des sélections après tri
- Mise à jour des indicateurs visuels

#### 3. TableColumn (dataclass)
**Responsabilité** : Définition des propriétés d'une colonne

**Attributs** :
- `ui_name` : Nom affiché
- `db_field` : Champ correspondant en DB
- `ui_index` : Position dans l'interface
- `db_index` : Position dans les données DB
- `is_computed` : Colonne calculée ou non
- `is_sortable` : Peut être triée
- `is_editable` : Peut être modifiée

## Avantages de la nouvelle architecture

### 1. Aucune perte de données
- Mapping permanent entre lignes affichées et IDs DB
- Validation avant chaque opération
- Transactions atomiques

### 2. Synchronisation parfaite
- Toutes les opérations passent par le mapping robuste
- Mise à jour cohérente entre affichage et base
- Rafraîchissement intelligent des colonnes calculées

### 3. Tri stable et reproductible
- Clé secondaire (ID) pour garantir l'ordre
- Comportement similaire à Excel
- Préservation des sélections

### 4. Extensibilité
- Ajout facile de nouvelles colonnes
- Support des colonnes calculées
- Configuration flexible des propriétés

## Utilisation

### Chargement des données
```python
# Via le TableDataManager
data = self.data_manager.load_data(search_term, column_filters)

# Le TableSortManager met à jour automatiquement l'affichage
self.sort_manager.refresh_table()
```

### Tri d'une colonne
```python
# Application d'un tri
self.sort_manager.apply_sort(column_index, SortOrder.ASC)

# Le tri préserve automatiquement :
# - L'intégrité des données
# - Les sélections utilisateur
# - La cohérence UI/DB
```

### Modification d'une cellule
```python
# Via le sort manager (mapping automatique)
success = self.sort_manager.handle_data_update(display_row, ui_column, new_value)

# Équivalent robuste de :
db_id = self.data_manager.get_db_id_for_row(display_row)
db_field = self.data_manager.get_db_field_by_ui_index(ui_column) 
self.db_manager.update_cell(db_id, db_field, new_value)
```

### Opérations sur les sélections
```python
# Récupération des IDs DB pour les lignes sélectionnées
selected_rows = [0, 2, 4]  # Lignes affichées
db_ids = self.data_manager.get_selected_db_ids(selected_rows)

# Les opérations utilisent les vrais IDs DB, pas les index affichés
for db_id in db_ids:
    self.db_manager.add_piece(piece_ref, db_id)
```

## Tests de validation

Le script `test_robust_sorting.py` valide :

1. **Chargement de base** : Structure et nombre de données
2. **Mapping des colonnes** : Correspondance UI ↔ DB
3. **Calcul des colonnes** : Nb Pièces dynamique
4. **Tri par colonne normale** : Type, Fabricant, etc.
5. **Tri par colonne calculée** : Nb Pièces
6. **Mapping après tri** : Cohérence des références
7. **Intégrité multiple tris** : Pas de perte après plusieurs tris
8. **Mise à jour avec tri** : Modification cohérente
9. **Éditabilité** : Propriétés des colonnes

## Migration depuis l'ancienne architecture

### Étapes de migration

1. **Remplacer MainWindow** par `EnhancedMainWindow`
2. **Importer les nouveaux modules** :
   ```python
   from src.ui.table_data_manager import TableDataManager
   from src.ui.table_sort_manager import TableSortManager
   ```

3. **Adapter les opérations existantes** :
   - Remplacer les accès directs aux index par les méthodes du data manager
   - Utiliser `get_db_id_for_row()` au lieu des en-têtes verticaux
   - Valider l'éditabilité avec `is_column_editable()`

4. **Tester les fonctionnalités critiques** :
   - Duplication par glisser-déposer
   - Complétion automatique
   - Ajout de pièces
   - Export des données

## Exemples concrets

### Avant (fragile)
```python
# ❌ Index fragile après tri
row = self.table.currentRow()
header_item = self.table.verticalHeaderItem(row)
db_id = int(header_item.text())

# ❌ Mapping colonne cassé
db_field_map = {0: 'type', 1: 'manufacturer', ...}
field_name = db_field_map.get(col)  # Incorrect après tri
```

### Après (robuste)
```python
# ✅ Mapping robuste
row = self.table.currentRow()
db_id = self.sort_manager.get_db_id_for_display_row(row)

# ✅ Mapping colonne stable
db_field = self.sort_manager.get_db_field_for_ui_column(col)
success = self.data_manager.update_cell(row, col, value)
```

Cette architecture garantit qu'aucune donnée ne sera jamais perdue lors du tri, et que toutes les opérations fonctionneront correctement quel que soit l'ordre d'affichage actuel.