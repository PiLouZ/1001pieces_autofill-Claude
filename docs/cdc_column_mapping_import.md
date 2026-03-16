# Cahier des charges — Mapping de colonnes à l'import

**Statut :** En cours — v3.30.0 (planifié)
**Version CDC :** 1.1
**Contexte :** L'application importe des fichiers CSV et PDF dont les colonnes sont détectées automatiquement par position. Certains fichiers fournisseurs ont des colonnes dans un ordre différent ou avec des champs supplémentaires que le système ne reconnaît pas. Ce CDC définit le mécanisme permettant à l'utilisateur de mapper manuellement les colonnes dans ce cas précis, sans altérer les formats existants reconnus.

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

- Permettre à l'utilisateur de mapper manuellement les colonnes d'un fichier **non reconnu**
- Conserver **intégralement** le comportement actuel pour les formats reconnus automatiquement
- Présenter les fichiers reconnus tel qu'aujourd'hui, avec leur aperçu, pour vérification avant import
- Gérer les imports multi-fichiers : fichiers reconnus + fichiers non reconnus coexistent dans le même dialogue
- Gérer les imports multi-fichiers avec structures hétérogènes (groupes de fichiers par nombre de colonnes)
- Garantir zéro régression sur tous les formats existants

---

## 2. Contrainte impérative — Formats existants protégés

Ces formats doivent fonctionner **à l'identique** après l'implémentation :

| Format | Colonnes | Mapping positionnel actuel | Priorité |
|---|---|---|---|
| PDF 3 col. (format principal) | 3 | col0→ref_modele, col1→commercial_ref, col2→third_col_choice | 🔴 Critique |
| CSV 1 col. | 1 | col0→ref_modele | 🔴 Critique |
| CSV 2 col. | 2 | col0→ref_modele, col1→commercial_ref | 🔴 Critique |
| CSV 3 col. | 3 | col0→ref_modele, col1→commercial_ref, col2→third_col_choice | 🔴 Critique |
| CSV 4+ col. | 4+ | col0→type, col1→fabricant, col2→ref_modele, col3→commercial_ref | 🔴 Critique |

**Règle absolue :**
- Le mapping manuel ne s'applique **qu'aux fichiers non reconnus**
- Un fichier reconnu ne passe **jamais** dans la logique de mapping, ni à l'affichage ni à l'import
- Quand `Config.ENABLE_COLUMN_MAPPING = False`, `_parse_row_data()` se comporte exactement comme avant

---

## 3. Modèle de données — Extensions

### 3.1 `ImportConfiguration` — nouveau champ

`column_mapping` devient un dictionnaire indexé par nombre de colonnes, permettant des mappings différents selon la structure du fichier :

```python
@dataclass
class ImportConfiguration:
    # ... champs existants inchangés ...

    # Mapping manuel : clé = nb colonnes, valeur = liste de destinations
    # None = comportement positionnel actuel pour tous les fichiers
    # Exemple : {4: ["type", "ref_modele", "ignore", "commercial_ref"],
    #            6: ["ref_modele", "commercial_ref", "type", "ignore", "ignore", "notes"]}
    column_mapping: Optional[Dict[int, List[str]]] = None
```

### 3.2 Valeurs de mapping acceptées

| Valeur string | Champ DB cible |
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
# Flag de feature : mapping manuel de colonnes (désactivé pendant développement)
ENABLE_COLUMN_MAPPING = False
```

---

## 4. Classification des fichiers à l'ouverture du dialogue

À l'ouverture de `ImportDialog`, chaque fichier est classé :

```
Pour chaque fichier :
    detected_columns = len(sample_data[0])
    si detected_columns dans {1, 2, 3, 4+} → RECONNU  (format positionnel connu)
    sinon                                   → NON RECONNU (nécessite mapping)
```

Cette classification pilote **l'affichage** (§5) et **l'import** (§6).

---

## 5. Interface utilisateur

### 5.1 Vue d'ensemble du dialogue

Le QGroupBox "Format reconnu et aperçu" est remplacé par une section structurée en deux blocs distincts, affichés seulement s'ils contiennent des fichiers :

```
┌─ Fichiers reconnus ─────────────────────────────────────────────────┐
│  (affiché uniquement s'il y a au moins un fichier reconnu)          │
│                                                                     │
│  ✓ PDF — 3 colonnes : fichier1.pdf, fichier2.pdf                    │
│  • 3 colonnes → Réf. technique + Réf. commerciale + Description     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Col1           Col2           Col3                         │    │
│  │  ============   ============   ============                 │    │
│  │  REF001         COMM001        Description...               │    │
│  │  REF002         COMM002        Description...               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ✓ CSV — 2 colonnes : fichier3.csv                                  │
│  • 2 colonnes → Réf. Modèle + Réf. Commerciale                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ...aperçu...                                               │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘

┌─ Fichiers non reconnus — mapping requis ────────────────────────────┐
│  (affiché uniquement s'il y a au moins un fichier non reconnu)      │
│                                                                     │
│  ⛔  fichier4.csv, fichier5.csv  (4 colonnes)                       │
│                                                                     │
│  Correspondance des colonnes :                                      │
│  Colonne 1  │  "VAL1A" / "VAL1B"  │  [▼ — Ignorer —          ]    │
│  Colonne 2  │  "VAL2A" / "VAL2B"  │  [▼ — Ignorer —          ]    │
│  Colonne 3  │  "VAL3A" / "VAL3B"  │  [▼ — Ignorer —          ]    │
│  Colonne 4  │  "VAL4A" / "VAL4B"  │  [▼ — Ignorer —          ]    │
│                                                                     │
│  ⛔  fichier6.csv  (6 colonnes)                                     │
│                                                                     │
│  Correspondance des colonnes :                                      │
│  Colonne 1  │  "AAA" / "BBB"      │  [▼ — Ignorer —          ]    │
│  ...                                                                │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 Bloc "Fichiers reconnus"

- Affiché **uniquement** s'il y a au moins un fichier reconnu
- Regroupé par structure (même nb de colonnes + même type)
- Pour chaque groupe : label de description du format + aperçu texte (comportement actuel conservé)
- Lecture seule : pas d'interaction, juste visualisation avant import

### 5.3 Bloc "Fichiers non reconnus"

- Affiché **uniquement** s'il y a au moins un fichier non reconnu
- Regroupé par nombre de colonnes détecté : un sous-bloc par groupe
- Chaque sous-bloc contient :
  - En-tête : `⛔ fichierA.csv, fichierB.csv (N colonnes)`
  - Widget de mapping : une ligne par colonne, avec exemples de valeurs + QComboBox
- Toutes les combos initialisées à `"— Ignorer —"`
- Bouton **Importer désactivé** tant qu'au moins un groupe non reconnu n'a pas `ref_modele` mappée
- Dès que tous les groupes ont `ref_modele` → bouton activé + en-tête passe à `⚠ fichierA.csv…` (orange)

### 5.4 Structure d'une ligne de mapping

```
Colonne N  │  "exemple1" / "exemple2"  │  [▼ destination ]
```

- Colonne gauche : `Colonne N` en gras, largeur fixe
- Colonne centre : 2 valeurs de `sample_data` (monospace, gris, tronquées à 18 car.), largeur fixe
- Colonne droite : QComboBox avec les 7 destinations (§3.2) + `"— Ignorer —"` par défaut

### 5.5 Validation inline

| Situation | Feedback visuel |
|---|---|
| Aucun `ref_modele` dans un groupe | En-tête rouge ⛔, bouton Importer désactivé |
| `ref_modele` mappée dans tous les groupes | En-tête orange ⚠, bouton activé |
| Doublon de destination dans un groupe (ex : 2×`ref_modele`) | Label d'avertissement sous le mapping du groupe, non bloquant |

---

## 6. Logique d'import — `_parse_row_data()`

```python
def _parse_row_data(self, row, config):
    n = len(row)

    # Si un mapping explicite existe pour ce nombre de colonnes → l'utiliser
    if config.column_mapping and n in config.column_mapping:
        data = {}
        for i, field in enumerate(config.column_mapping[n]):
            if i < n and field != "ignore":
                data[field] = row[i]
        return data

    # Sinon : comportement POSITIONNEL ACTUEL inchangé (fallback)
    # ... code existant intact, pas une ligne modifiée ...
```

Le fallback positionnel est **le chemin par défaut** — il s'exécute pour tous les fichiers reconnus et quand `column_mapping` est `None`.

---

## 7. Plan d'implémentation par phases

### Phase 1 — Infrastructure (savepoint `v3.29.3`)
**Objectif :** Préparer le socle sans rien casser. Flag désactivé. Aucun changement visible.

- [ ] Ajouter `column_mapping: Optional[Dict[int, List[str]]] = None` dans `ImportConfiguration`
- [ ] Ajouter `Config.ENABLE_COLUMN_MAPPING = False`
- [ ] Modifier `_parse_row_data()` : branchement `column_mapping[n]` si présent, sinon fallback
- [ ] **Tous les tests non-régression §8.1 doivent passer**
- [ ] Commit + tag savepoint `v3.29.3`

### Phase 2 — Classification et affichage (savepoint `v3.29.4`)
**Objectif :** Refactoriser `_analyze_formats_and_preview()` pour séparer reconnus / non reconnus.

- [ ] Créer `_classify_files()` → retourne `(recognized, unrecognized_groups)`
- [ ] Refactoriser l'affichage en deux blocs (§5.1) — caché si `ENABLE_COLUMN_MAPPING = False`
- [ ] Conserver l'affichage actuel intact quand le flag est `False`
- [ ] **Tous les tests §8.1 + §8.2 doivent passer**
- [ ] Commit + tag savepoint `v3.29.4`

### Phase 3 — Widget de mapping (savepoint `v3.29.5`)
**Objectif :** Construire `MappingGroupWidget`, l'intégrer, gérer la validation.

- [ ] Créer `MappingGroupWidget(QWidget)` : N lignes colonne/exemples/combo
- [ ] Intégrer dans le bloc "non reconnus" pour chaque groupe
- [ ] `_validate_and_accept()` : lire tous les groupes → construire `config.column_mapping`
- [ ] Gestion de l'activation/désactivation du bouton Importer (§5.5)
- [ ] **Tous les tests §8.1 + §8.2 + §8.3 doivent passer**
- [ ] Commit + tag savepoint `v3.29.5`

### Phase 4 — Activation et release (release `v3.30.0`)
**Objectif :** Activer le flag, tests end-to-end, documentation.

- [ ] `Config.ENABLE_COLUMN_MAPPING = True`
- [ ] Tests §8.4 avec fichiers réels
- [ ] Vérification visuelle complète du dialogue
- [ ] Mise à jour `CHANGELOG.md` et `README.md`
- [ ] Commit + tag `v3.30.0`

---

## 8. Tests de non-régression

### 8.1 Tests Phase 1 — `_parse_row_data()` uniquement

| # | Scénario | Input | Résultat attendu |
|---|---|---|---|
| T1.1 | CSV 1 col, pas de mapping | `["REF001"]`, `column_mapping=None` | `ref_modele="REF001"` |
| T1.2 | CSV 2 col, pas de mapping | `["REF001","COMM1"]`, `column_mapping=None` | `ref_modele="REF001"`, `commercial_ref="COMM1"` |
| T1.3 | CSV 3 col, other_ref, pas de mapping | `["R","C","A"]`, `third_column_choice="other_ref"`, `column_mapping=None` | `ref_modele="R"`, `commercial_ref="C"`, `other_ref="A"` |
| T1.4 | CSV 4 col, pas de mapping | `["Type","Fab","Ref","Comm"]`, `column_mapping=None` | `type="Type"`, `manufacturer="Fab"`, `ref_modele="Ref"`, `commercial_ref="Comm"` |
| T1.5 | PDF 3 col, pas de mapping | `["R","C","D"]`, `column_mapping=None` | identique à T1.3 selon `third_column_choice` |
| T1.6 | Mapping manuel 4 col | `["A","B","C","D"]`, `column_mapping={4:["ref_modele","commercial_ref","ignore","type"]}` | `ref_modele="A"`, `commercial_ref="B"`, `type="D"` |
| T1.7 | Mapping avec ignore | `["REF","X"]`, `column_mapping={2:["ref_modele","ignore"]}` | `ref_modele="REF"` uniquement |
| T1.8 | Mapping pour N col absent (fallback) | `["A","B"]`, `column_mapping={4:["ref_modele","commercial_ref","ignore","type"]}` | fallback positionnel : `ref_modele="A"`, `commercial_ref="B"` |

### 8.2 Tests Phase 2 — Classification des fichiers

| # | Scénario | Résultat attendu |
|---|---|---|
| T2.1 | Import seul — PDF 3 col | Bloc "reconnus" affiché, pas de bloc "non reconnus" |
| T2.2 | Import seul — format inconnu 5 col | Bloc "non reconnus" affiché, pas de bloc "reconnus" |
| T2.3 | Multi-fichiers — 2 PDF 3 col + 1 CSV 5 col inconnu | Les 2 blocs affichés |
| T2.4 | Multi-fichiers — 2 CSV inconnus 4 col + 1 CSV inconnu 6 col | Bloc "non reconnus" avec 2 sous-groupes (4 col et 6 col) |
| T2.5 | Multi-fichiers — tous reconnus | Seul le bloc "reconnus" affiché, comportement identique à aujourd'hui |

### 8.3 Tests Phase 3 — Widget de mapping

| # | Scénario | Action | Résultat attendu |
|---|---|---|---|
| T3.1 | Fichier non reconnu ouvert | Observer | Toutes combos à "Ignorer", bouton Importer désactivé |
| T3.2 | Mapper ref_modele sur col1 | Sélectionner dans combo | Bouton Importer activé, en-tête passe en orange |
| T3.3 | 2 groupes non reconnus, mapper 1 seul | Mapper uniquement groupe 1 | Bouton reste désactivé (groupe 2 sans ref_modele) |
| T3.4 | Doublon ref_modele dans même groupe | Mapper 2 colonnes → ref_modele | Avertissement non bloquant affiché |
| T3.5 | Import PDF 3 col (reconnu) sans toucher au mapping | Importer | Données identiques à avant la feature |

### 8.4 Tests Phase 4 — End-to-end avec fichiers réels

| # | Fichier test | Validation |
|---|---|---|
| T4.1 | PDF fournisseur habituel (3 col) | Vérifier 5 enregistrements en DB = valeurs attendues |
| T4.2 | CSV 2 col standard | Vérifier ref_modele + commercial_ref corrects |
| T4.3 | CSV ordre inversé (commercial en col0) | Mapper manuellement, vérifier import correct |
| T4.4 | CSV 5 col avec champs non standard | Mapper 3 colonnes utiles, ignorer les 2 autres |
| T4.5 | Mix : 2 PDF reconnus + 1 CSV inconnu | PDF importés normalement + CSV avec mapping correct |

---

## 9. Savepoints et rollback

| Savepoint | Tag git | Description |
|---|---|---|
| Stable actuel | `v3.29.2` | État avant tout développement — rollback ici si blocage |
| Fin Phase 1 | `v3.29.3` | Infrastructure `column_mapping`, flag désactivé |
| Fin Phase 2 | `v3.29.4` | Classification fichiers, affichage deux blocs, flag désactivé |
| Fin Phase 3 | `v3.29.5` | Widget mapping complet, flag désactivé |
| Release | `v3.30.0` | Flag activé, feature complète |

**Rollback immédiat sans perte :**
```bash
# Option 1 : retour git complet
git checkout v3.29.2

# Option 2 : désactivation du flag seul (sans rollback code)
Config.ENABLE_COLUMN_MAPPING = False
```

---

## 10. Fichiers modifiés (périmètre)

| Fichier | Modifications |
|---|---|
| `src/core/config.py` | + `ENABLE_COLUMN_MAPPING = False` |
| `src/core/import_manager.py` | + `_classify_files()`, `MappingGroupWidget`, refacto `_analyze_formats_and_preview()`, branchement `_parse_row_data()`, lecture mapping dans `_validate_and_accept()` |
| `CHANGELOG.md` | Entrées v3.29.3 → v3.30.0 |
| `README.md` | Version + section Import |

**Fichiers NON modifiés :**
- `src/data/database_manager.py` — aucun changement DB
- `src/ui/*` — aucun impact interface principale
- `_execute_import()`, `_import_single_file()`, batch processing — **inchangés**

---

*CDC v1.1 — mis à jour le 2026-03-16*
*Changements v1.1 : scope restreint aux formats non reconnus uniquement ; gestion multi-fichiers par groupes de structure ; présentation des fichiers reconnus inchangée (lecture seule) ; 4 phases au lieu de 3.*
