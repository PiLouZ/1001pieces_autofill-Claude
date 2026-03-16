# Cahier des charges — Mapping de colonnes à l'import

**Statut :** Livré — v3.30.0
**Version CDC :** 1.2
**Contexte :** L'application importe des fichiers CSV et PDF dont les colonnes sont détectées et mappées automatiquement par position. Ce CDC définit une option de personnalisation du mapping, discrète pour les formats reconnus, obligatoire pour les formats non reconnus.

---

## 0. Convention de versioning (appliquée à partir de v3.30.0)

| Position | Signification | Exemple |
|---|---|---|
| **X** (premier) | Version majeure — refonte architecturale | `3.x.x` |
| **Y** (deuxième) | Fonctionnalité majeure ajoutée | `3.30.0` ← mapping colonnes |
| **Z** (troisième) | Correctif ou ajustement mineur | `3.30.1`, `3.30.2` |

Historique rétrospectivement renuméroté :
- `3.29.0` → base (PiecePickerDialog, RefTagList)
- `3.29.1` → Fix panneau pièces vidé sur perte de sélection
- `3.29.2` → Fix stabilité UI + alerte format import non reconnu ← *dernier commit*

---

## 1. Objectifs

- Conserver **intégralement** le comportement actuel pour les imports non modifiés
- Offrir une option discrète de personnalisation du mapping pour **tous** les formats
- Rendre le mapping **obligatoire et déplié** pour les formats non reconnus
- Gérer les imports multi-fichiers avec structures hétérogènes : un mapping par groupe de colonnes
- Garantir zéro régression — si l'utilisateur ne touche pas à l'option, tout se comporte comme avant

---

## 2. Formats reconnus (rappel — inchangés)

### 2.1 Filtrage par extension

| Extension | Résultat |
|---|---|
| `.csv` | Accepté |
| `.pdf` | Accepté |
| Toute autre | Rejeté immédiatement (pas de dialogue) |

### 2.2 Mapping positionnel actuel selon le nombre de colonnes

| Colonnes | Label affiché | Mapping par défaut (`_parse_row_data`) |
|---|---|---|
| 0 | ⛔ Format non reconnu | — import bloqué |
| 1 | ✓ 1 colonne | `col0 → ref_modele` |
| 2 | ✓ 2 colonnes | `col0 → ref_modele` · `col1 → commercial_ref` |
| 3 (CSV) | ✓ 3 colonnes | `col0 → ref_modele` · `col1 → commercial_ref` · `col2 → third_col_choice` |
| 3 (PDF) | ✓ 3 colonnes | `col0 → ref_modele` · `col1 → commercial_ref` · `col2 → third_col_choice` |
| 4 | ✓ 4+ colonnes | `col0 → type` · `col1 → fabricant` · `col2 → ref_modele` · `col3 → commercial_ref` |
| 5 | ✓ 4+ colonnes | idem 4 + `col4 → third_col_choice` |
| 6+ | ✓ 4+ colonnes | idem 5 — **colonnes 6+ ignorées silencieusement** |

**Règle absolue :** si l'utilisateur ne touche pas à l'option de mapping, ces correspondances s'appliquent **exactement comme aujourd'hui**, sans aucune modification de comportement.

---

## 3. Modèle de données — Extensions

### 3.1 `ImportConfiguration` — nouveau champ

```python
@dataclass
class ImportConfiguration:
    # ... champs existants inchangés ...

    # Mapping personnalisé par nombre de colonnes.
    # None = comportement positionnel actuel pour tous les fichiers (défaut).
    # Clé   : nombre de colonnes du groupe de fichiers
    # Valeur : liste de N destinations (une par colonne)
    # Exemple : {3: ["commercial_ref", "ref_modele", "ignore"],
    #            6: ["ref_modele", "commercial_ref", "type", "ignore", "ignore", "notes"]}
    column_mapping: Optional[Dict[int, List[str]]] = None
```

### 3.2 Destinations valides

| Valeur | Champ DB |
|---|---|
| `"type"` | Type d'appareil |
| `"manufacturer"` | Fabricant |
| `"ref_modele"` | Référence Modèle |
| `"commercial_ref"` | Référence Commerciale |
| `"other_ref"` | Autre Référence |
| `"notes"` | Notes |
| `"ignore"` | Colonne ignorée |

### 3.3 `Config` — nouveau flag

```python
# Flag de feature : option de mapping de colonnes (activé depuis v3.30.0)
ENABLE_COLUMN_MAPPING = True
```

---

## 4. Comportement attendu par cas

### 4.1 Format reconnu — import standard (aucun changement)

1. Format détecté → label "✓ Format reconnu : N colonnes" + description + aperçu (identique à aujourd'hui)
2. Option discrète `▶ Adapter le mapping` — **repliée par défaut**
3. L'utilisateur n'y touche pas → import identique à aujourd'hui

### 4.2 Format reconnu — import avec mapping personnalisé

1. L'utilisateur clique `▶ Adapter le mapping` → widget déplié, combos **pré-remplies** selon le mapping par défaut du format détecté
2. L'utilisateur modifie une ou plusieurs combos
3. `_validate_and_accept()` stocke le mapping dans `config.column_mapping`
4. `_parse_row_data()` utilise ce mapping au lieu du positionnel

### 4.3 Format non reconnu

1. Bandeau rouge ⛔ affiché (déjà implémenté)
2. Widget de mapping **déplié et non repliable** — toutes combos à `"— Ignorer —"`
3. Bouton **Importer désactivé** tant qu'aucune colonne n'est assignée à `ref_modele`
4. Dès qu'une colonne est assignée à `ref_modele` → bouton activé + bandeau passe en orange ⚠

### 4.4 Multi-fichiers — même structure

- Cas le plus fréquent (ex : 5 PDF du même fournisseur)
- Un seul widget de mapping, appliqué à tous les fichiers du groupe
- Comportement identique aux cas 4.1 / 4.3 selon si le format est reconnu ou non

### 4.5 Multi-fichiers — structures hétérogènes

Les fichiers sont regroupés par nombre de colonnes détecté. Chaque groupe a son propre widget :

```
Groupe 1 — fichier1.pdf, fichier2.pdf  (3 colonnes — reconnu)
    ▶ Adapter le mapping  ← replié par défaut

Groupe 2 — fichier3.csv, fichier4.csv  (4 colonnes — reconnu)
    ▶ Adapter le mapping  ← replié par défaut

Groupe 3 — fichier5.csv  (7 colonnes — non reconnu)
    ⛔ Mapping requis  ← déplié, obligatoire
```

Le bouton **Importer** reste désactivé tant que tous les groupes non reconnus n'ont pas `ref_modele` mappée.

---

## 5. Interface utilisateur

### 5.1 Vue d'ensemble

La section "Format reconnu et aperçu" existante est enrichie. Pour un import mono-fichier reconnu :

```
┌─ Format reconnu et aperçu ─────────────────────────────────────────┐
│  ✓ PDF — 3 colonnes                                                 │
│  • 3 colonnes → Réf. technique + Réf. commerciale + Description     │
│  ┌─ aperçu ──────────────────────────────────────────────────────┐  │
│  │  Col1           Col2           Col3                           │  │
│  │  ====           ====           ====                           │  │
│  │  REF001         COMM001        Description...                 │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ▶ Adapter le mapping                          ← discret, replié   │
└─────────────────────────────────────────────────────────────────────┘
```

Quand `▶ Adapter le mapping` est déplié :

```
│  ▼ Adapter le mapping                                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Colonne 1  │  "REF001" / "REF002"   │  [▼ Réf. Modèle   ]  │  │
│  │  Colonne 2  │  "COMM001" / "COMM002" │  [▼ Réf. Comm.    ]  │  │
│  │  Colonne 3  │  "Desc…" / "Desc…"    │  [▼ Ignorer       ]  │  │
│  └─────────────────────────────────────────────────────────────┘   │
```

Pour un format non reconnu, même widget mais toujours déplié, titre `⛔ Mapping requis` :

```
│  ⛔ Mapping requis — ce fichier ne sera pas importé sans mapping    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Colonne 1  │  "???" / "???"         │  [▼ — Ignorer —   ]  │  │
│  │  ...                                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
```

### 5.2 Structure d'une ligne de mapping

```
Colonne N  │  "exemple1" / "exemple2"  │  [▼ destination    ]
```

- Colonne gauche : `Colonne N` en gras, largeur fixe
- Colonne centre : 2 valeurs tirées de `sample_data` (monospace, gris, tronquées à 18 car.)
- Colonne droite : QComboBox avec les 7 destinations + `"— Ignorer —"` par défaut

### 5.3 Validation inline

| Situation | Feedback |
|---|---|
| Groupe non reconnu sans `ref_modele` | En-tête rouge ⛔, bouton Importer désactivé |
| Groupe non reconnu avec `ref_modele` | En-tête orange ⚠, bouton activé |
| Doublon de destination dans un groupe | Avertissement non bloquant sous le widget |
| Tous les groupes reconnus, mapping non touché | Bouton activé, comportement actuel |

---

## 6. Logique de `_parse_row_data()`

```python
def _parse_row_data(self, row, config):
    n = len(row)

    # Si un mapping personnalisé existe pour ce nombre de colonnes → l'utiliser
    if config.column_mapping and n in config.column_mapping:
        data = {}
        for i, field in enumerate(config.column_mapping[n]):
            if i < n and field != "ignore":
                data[field] = row[i]
        return data

    # Sinon : comportement POSITIONNEL ACTUEL inchangé (fallback)
    # ... code existant intact, aucune ligne modifiée ...
```

Le fallback positionnel est le **chemin par défaut** — il s'exécute pour tous les fichiers dont le mapping n'a pas été personnalisé.

---

## 7. Plan d'implémentation par phases

### Phase 1 — Infrastructure (savepoint `v3.29.3`) ✅
**Objectif :** Préparer le socle. Flag désactivé, aucun changement visible.

- [x] Ajouter `column_mapping: Optional[Dict[int, List[str]]] = None` dans `ImportConfiguration`
- [x] Ajouter `Config.ENABLE_COLUMN_MAPPING = False`
- [x] Modifier `_parse_row_data()` : branchement `column_mapping[n]` si présent, sinon fallback
- [x] **Tous les tests §8.1 ont passé**
- [x] Commit + tag `v3.29.3`

### Phase 2 — Classification et groupes (savepoint `v3.29.4`) ✅
**Objectif :** Regrouper les fichiers par structure, préparer l'affichage.

- [x] Créer `_group_files_by_columns()` → `Dict[int, List[ImportFile]]`
- [x] Refactoriser `_analyze_formats_and_preview()` pour itérer sur les groupes
- [x] Conserver l'affichage actuel quand `ENABLE_COLUMN_MAPPING = False`
- [x] **Tous les tests §8.1 + §8.2 ont passé**
- [x] Commit + tag `v3.29.4`

### Phase 3 — Widget de mapping (savepoint `v3.29.5`) ✅
**Objectif :** Construire `MappingGroupWidget`, intégrer l'option discrète et le mode obligatoire.

- [x] Créer `MappingGroupWidget(QWidget)` : toggle discret + N lignes colonne/exemples/combo
- [x] Format reconnu : widget replié, pré-rempli selon mapping positionnel du format
- [x] Format non reconnu : widget déplié, non repliable, combos à "Ignorer"
- [x] `_validate_and_accept()` : construire `config.column_mapping` depuis les widgets modifiés
- [x] Gestion activation/désactivation bouton Importer (§5.3)
- [x] **Tous les tests §8.1 + §8.2 + §8.3 ont passé**
- [x] Commit + tag `v3.29.5`

### Phase 4 — Activation et release (release `v3.30.0`) ✅
**Objectif :** Activer le flag, tests end-to-end, documentation.

- [x] `Config.ENABLE_COLUMN_MAPPING = True`
- [ ] Tests §8.4 avec fichiers réels (à valider par l'utilisateur)
- [ ] Vérification visuelle complète (à valider par l'utilisateur)
- [x] Mise à jour version `3.30.0` dans `config.py`
- [x] Commit + tag `v3.30.0`

---

## 8. Tests de non-régression

### 8.1 Phase 1 — `_parse_row_data()` uniquement

| # | Scénario | Input | Résultat attendu |
|---|---|---|---|
| T1.1 | 1 col, pas de mapping | `["REF001"]`, `column_mapping=None` | `ref_modele="REF001"` |
| T1.2 | 2 col, pas de mapping | `["REF001","COMM1"]`, `column_mapping=None` | `ref_modele="REF001"`, `commercial_ref="COMM1"` |
| T1.3 | 3 col, other_ref, pas de mapping | `["R","C","A"]`, `third_column_choice="other_ref"`, `column_mapping=None` | `ref_modele="R"`, `commercial_ref="C"`, `other_ref="A"` |
| T1.4 | 4 col, pas de mapping | `["Type","Fab","Ref","Comm"]`, `column_mapping=None` | `type="Type"`, `manufacturer="Fab"`, `ref_modele="Ref"`, `commercial_ref="Comm"` |
| T1.5 | PDF 3 col, pas de mapping | `["R","C","D"]`, `column_mapping=None` | identique à T1.3 |
| T1.6 | Mapping personnalisé 4 col | `["A","B","C","D"]`, `column_mapping={4:["ref_modele","commercial_ref","ignore","type"]}` | `ref_modele="A"`, `commercial_ref="B"`, `type="D"` |
| T1.7 | Mapping avec ignore | `["REF","X"]`, `column_mapping={2:["ref_modele","ignore"]}` | `ref_modele="REF"` uniquement |
| T1.8 | Mapping pour N absent → fallback | `["A","B"]`, `column_mapping={4:["ref_modele","commercial_ref","ignore","type"]}` | fallback : `ref_modele="A"`, `commercial_ref="B"` |
| T1.9 | Mapping présent mais vide pour N → fallback | `["A","B"]`, `column_mapping={}` | fallback : `ref_modele="A"`, `commercial_ref="B"` |

### 8.2 Phase 2 — Groupement des fichiers

| # | Scénario | Résultat attendu |
|---|---|---|
| T2.1 | 1 fichier PDF 3 col | 1 groupe (3 col, reconnu) |
| T2.2 | 3 fichiers PDF 3 col | 1 groupe (3 col, reconnu) |
| T2.3 | 2 PDF 3 col + 1 CSV 5 col inconnu | 2 groupes (3 col reconnu + 5 col non reconnu) |
| T2.4 | 2 CSV 4 col + 1 CSV 6 col | 2 groupes (4 col + 6 col, tous reconnus) |
| T2.5 | 1 CSV 0 col (vide) | 1 groupe (0 col, non reconnu) |

### 8.3 Phase 3 — Widget de mapping

| # | Scénario | Action | Résultat attendu |
|---|---|---|---|
| T3.1 | Fichier reconnu, mapping non touché | Importer | Comportement identique à avant |
| T3.2 | Fichier reconnu, ouvrir toggle | Cliquer `▶ Adapter le mapping` | Widget déplié, combos pré-remplies selon format détecté |
| T3.3 | Fichier non reconnu | Ouvrir dialogue | Widget déplié non repliable, combos à "Ignorer", Importer désactivé |
| T3.4 | Fichier non reconnu, mapper ref_modele | Sélectionner combo | Importer activé, bandeau orange |
| T3.5 | 2 groupes non reconnus, mapper 1 seul | — | Importer reste désactivé |
| T3.6 | Doublon ref_modele | Mapper 2 colonnes → ref_modele | Avertissement affiché, non bloquant |
| T3.7 | PDF 3 col sans toucher mapping | Importer | Données en DB identiques à avant la feature |

### 8.4 Phase 4 — End-to-end

| # | Fichier | Validation |
|---|---|---|
| T4.1 | PDF fournisseur standard (3 col) | 5 enregistrements DB = valeurs attendues |
| T4.2 | CSV 2 col standard | ref_modele + commercial_ref corrects |
| T4.3 | CSV ordre inversé (commercial en col0) | Mapper manuellement, vérifier import |
| T4.4 | CSV 7 col non reconnu | Mapper 4 colonnes utiles, ignorer les 3 autres |
| T4.5 | Mix : 2 PDF reconnus + 1 CSV inconnu | PDF importés normalement + CSV avec mapping |

---

## 9. Savepoints et rollback

| Savepoint | Tag git | Description |
|---|---|---|
| Stable actuel | `v3.29.2` | État avant tout développement |
| Fin Phase 1 | `v3.29.3` | Infrastructure, flag désactivé |
| Fin Phase 2 | `v3.29.4` | Groupement fichiers, flag désactivé |
| Fin Phase 3 | `v3.29.5` | Widget complet, flag désactivé |
| Release | `v3.30.0` | Flag activé, feature complète |

```bash
git checkout v3.29.2        # rollback complet
# OU
Config.ENABLE_COLUMN_MAPPING = False   # désactivation sans rollback
```

---

## 10. Périmètre des modifications

| Fichier | Modifications |
|---|---|
| `src/core/config.py` | + `ENABLE_COLUMN_MAPPING = False` |
| `src/core/import_manager.py` | + `_group_files_by_columns()`, `MappingGroupWidget`, refacto `_analyze_formats_and_preview()`, branchement `_parse_row_data()`, lecture mapping `_validate_and_accept()` |
| `CHANGELOG.md` | Entrées v3.29.3 → v3.30.0 |
| `README.md` | Version + section Import |

**Fichiers NON modifiés :**
- `src/data/database_manager.py`
- `src/ui/*`
- `_execute_import()`, `_import_single_file()`, batch processing

---

*CDC v1.2 — mis à jour le 2026-03-16*
*Changements v1.2 : option de mapping disponible pour tous les formats (discrète/repliée pour les reconnus, obligatoire/dépliée pour les non reconnus) ; multi-fichiers par groupes de structure.*
*Phase 4 complétée le 2026-03-16 — flag activé, v3.30.0 livrée. Tests §8.4 (end-to-end avec fichiers réels) à valider par l'utilisateur.*
