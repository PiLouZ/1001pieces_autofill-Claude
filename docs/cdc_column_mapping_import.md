# Cahier des charges — Mapping de colonnes à l'import

**Statut :** En cours — v3.30.0 (planifié)
**Version CDC :** 1.0
**Contexte :** L'application importe des fichiers CSV et PDF dont les colonnes sont détectées automatiquement par position. Certains fichiers fournisseurs ont des colonnes dans un ordre différent ou avec des champs supplémentaires. Ce CDC définit le mécanisme permettant à l'utilisateur de mapper manuellement les colonnes, sans altérer les formats existants.

---

## 0. Convention de versioning (appliquée à partir de v3.30.0)

| Position | Signification | Exemple |
|---|---|---|
| **X** (premier) | Version majeure — refonte architecturale | `3.x.x` |
| **Y** (deuxième) | Fonctionnalité majeure ajoutée | `3.30.0` ← colonne mapping |
| **Z** (troisième) | Correctif ou ajustement mineur | `3.30.1`, `3.30.2` |

Les correctifs et ajustements mineurs de la session précédente sont renumérotés rétrospectivement :
- `3.29.0` → base (PiecePickerDialog, RefTagList, v3.29.0)
- `3.29.1` → Fix panneau pièces vidé sur perte de sélection
- `3.29.2` → Fix stabilité UI + alerte format import non reconnu ← *dernier commit*

---

## 1. Objectifs

- Permettre à l'utilisateur de définir quel champ DB correspond à quelle colonne du fichier
- Conserver **intégralement** le comportement actuel pour les formats détectés automatiquement
- Rendre l'import possible pour des fichiers dont le format n'est pas reconnu automatiquement
- Intégrer le mapping dans l'interface existante (`ImportDialog`), sans nouvelle fenêtre
- Garantir zéro régression sur le format PDF 3 colonnes et tous les formats CSV existants

---

## 2. Contrainte impérative — Formats existants protégés

Le tableau suivant définit les formats **actuels** qui doivent fonctionner **à l'identique** après l'implémentation :

| Format | Colonnes | Mapping actuel (positionnel) | Priorité |
|---|---|---|---|
| PDF 3 col. (format principal) | 3 | col0→ref_modele, col1→commercial_ref, col2→third_col_choice | 🔴 Critique |
| CSV 1 col. | 1 | col0→ref_modele | 🔴 Critique |
| CSV 2 col. | 2 | col0→ref_modele, col1→commercial_ref | 🔴 Critique |
| CSV 3 col. | 3 | col0→ref_modele, col1→commercial_ref, col2→third_col_choice | 🔴 Critique |
| CSV 4+ col. | 4+ | col0→type, col1→fabricant, col2→ref_modele, col3→commercial_ref | 🔴 Critique |

**Règle absolue :** quand `Config.ENABLE_COLUMN_MAPPING = False` (valeur par défaut initiale), `_parse_row_data()` doit se comporter **exactement** comme avant. Le mapping manuel n'intervient **que** si `column_mapping` est explicitement renseigné dans `ImportConfiguration`.

---

## 3. Modèle de données — Extensions

### 3.1 `ImportConfiguration` — nouveau champ

```python
@dataclass
class ImportConfiguration:
    # ... champs existants inchangés ...

    # Mapping manuel des colonnes (None = comportement positionnel actuel)
    # Liste de N chaînes pour N colonnes détectées
    # Valeurs possibles : voir §3.2
    column_mapping: Optional[List[str]] = None
```

### 3.2 Valeurs de mapping acceptées

| Valeur string | Champ DB cible | Notes |
|---|---|---|
| `"type"` | `type` | Type d'appareil |
| `"manufacturer"` | `manufacturer` | Fabricant |
| `"ref_modele"` | `ref_modele` | Référence Modèle |
| `"commercial_ref"` | `commercial_ref` | Référence Commerciale |
| `"other_ref"` | `other_ref` | Autre Référence |
| `"notes"` | `notes` | Notes |
| `"ignore"` | — | Colonne ignorée |

### 3.3 `Config` — nouveau flag

```python
# Flag de feature : mapping manuel de colonnes (désactivé pendant développement)
ENABLE_COLUMN_MAPPING = False
```

---

## 4. Comportement attendu

### 4.1 Format reconnu automatiquement (cas nominal, inchangé)

1. Le format est détecté → format_info_label affiche "Format reconnu : N colonnes"
2. Si `ENABLE_COLUMN_MAPPING = True` : widget de mapping visible, **pré-rempli** selon le format détecté, repliable
3. L'utilisateur peut ajuster (ou ne pas toucher)
4. À l'import : `column_mapping` utilisé si modifié, sinon fallback positionnel classique

### 4.2 Format non reconnu (cas nouveau)

1. Bandeau rouge "⛔ Format non reconnu" affiché (déjà implémenté)
2. Widget de mapping **obligatoirement visible et déplié**
3. Toutes les colonnes initialisées à `"ignore"`
4. Bouton "Importer" reste **désactivé** tant qu'aucune colonne n'est mappée sur `"ref_modele"` (minimum requis)
5. Dès qu'une colonne est assignée à `"ref_modele"` → bouton activé + bandeau rouge remplacé par bandeau orange "⚠ Mapping manuel — vérifiez la correspondance avant d'importer"

### 4.3 Validation avant import

| Condition | Comportement |
|---|---|
| Aucune colonne → `ref_modele` | Import bloqué, message d'erreur inline |
| Doublon de destination (ex : 2 colonnes → `ref_modele`) | Warning non-bloquant dans le widget |
| Mapping valide | Import autorisé |

---

## 5. Interface utilisateur

### 5.1 Emplacement du widget de mapping

Dans `ImportDialog`, **entre** `format_desc_label` et `preview_text`, au sein du QGroupBox "Format reconnu et aperçu" existant.

### 5.2 Structure du widget

```
┌─ Correspondance des colonnes ──────────────────────────────────────┐
│                                                                     │
│  Colonne 1   │  "REF001" / "REF002"  │  [▼ Référence Modèle    ]  │
│  Colonne 2   │  "COMM-A" / "COMM-B"  │  [▼ Réf. Commerciale    ]  │
│  Colonne 3   │  "DESC1"  / "DESC2"   │  [▼ Ignorer             ]  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

- Une ligne par colonne détectée
- Colonne gauche : label "Colonne N" (gras)
- Colonne centre : 2 exemples de valeurs tirés de `sample_data` (gris, monospace, tronqués à 20 car.)
- Colonne droite : QComboBox de destination
- Pour format reconnu : widget repliable via chevron ▶/▼ "Personnaliser le mapping"
- Pour format non reconnu : widget toujours déplié, non repliable

### 5.3 Intégration avec la section existante

Pour format reconnu → `format_warning_widget` caché, `mapping_widget` repliable
Pour format non reconnu → `format_warning_widget` remplacé par avertissement orange après mapping partiel

---

## 6. Logique de `_parse_row_data()` après implémentation

```python
def _parse_row_data(self, row, config):
    if config.column_mapping:
        # Mode mapping manuel : utiliser la correspondance explicite
        data = {}
        for i, field in enumerate(config.column_mapping):
            if i < len(row) and field != "ignore":
                data[field] = row[i]
        return data
    else:
        # Mode positionnel : comportement ACTUEL inchangé (fallback)
        # ... code existant intact ...
```

---

## 7. Plan d'implémentation par phases

### Phase 1 — Infrastructure (savepoint `v3.29.3`)
**Objectif :** Préparer le socle sans rien casser. Flag désactivé.

- [ ] Ajouter `column_mapping: Optional[List[str]] = None` dans `ImportConfiguration`
- [ ] Ajouter `Config.ENABLE_COLUMN_MAPPING = False`
- [ ] Modifier `_parse_row_data()` : si `column_mapping` présent → l'utiliser, sinon fallback
- [ ] **Tests non-régression Phase 1** (voir §8) — tous doivent passer
- [ ] Commit savepoint `v3.29.3`

### Phase 2 — Widget de mapping (savepoint `v3.29.4`)
**Objectif :** Construire et intégrer le widget dans le dialogue, sans l'activer.

- [ ] Créer `MappingWidget` (QWidget dédié, dans `import_manager.py`)
- [ ] Intégrer dans `ImportDialog._init_ui()` — caché si `ENABLE_COLUMN_MAPPING = False`
- [ ] `_analyze_formats_and_preview()` : pré-remplir les combos selon format détecté
- [ ] `_validate_and_accept()` : lire les combos et renseigner `config.column_mapping`
- [ ] Gestion de la validation (§4.3)
- [ ] **Tests non-régression Phase 2** (voir §8) — tous doivent passer
- [ ] Commit savepoint `v3.29.4`

### Phase 3 — Activation et polish (release `v3.30.0`)
**Objectif :** Activer le flag, valider visuellement, documenter.

- [ ] `Config.ENABLE_COLUMN_MAPPING = True`
- [ ] Tests end-to-end avec fichiers réels (PDF 3 col, CSV variés, format inconnu)
- [ ] Vérification visuelle de l'alignement dans le dialogue
- [ ] Mise à jour `CHANGELOG.md` et `README.md`
- [ ] Commit release `v3.30.0`

---

## 8. Tests de non-régression

### 8.1 Tests Phase 1 — `_parse_row_data()` uniquement

| # | Scénario | Input | Résultat attendu |
|---|---|---|---|
| T1.1 | CSV 1 col, pas de mapping | `["REF001"]`, `column_mapping=None` | `ref_modele="REF001"` |
| T1.2 | CSV 2 col, pas de mapping | `["REF001","COMM1"]`, `column_mapping=None` | `ref_modele="REF001"`, `commercial_ref="COMM1"` |
| T1.3 | CSV 3 col, other_ref, pas de mapping | `["R","C","A"]`, `third_column_choice="other_ref"`, `column_mapping=None` | `ref_modele="R"`, `commercial_ref="C"`, `other_ref="A"` |
| T1.4 | CSV 4 col, pas de mapping | `["Type","Fab","Ref","Comm"]`, `column_mapping=None` | `type="Type"`, `manufacturer="Fab"`, `ref_modele="Ref"`, `commercial_ref="Comm"` |
| T1.5 | Mapping manuel simple | `["AAA","BBB"]`, `column_mapping=["commercial_ref","ref_modele"]` | `commercial_ref="AAA"`, `ref_modele="BBB"` |
| T1.6 | Mapping avec ignore | `["REF","IGNORE"]`, `column_mapping=["ref_modele","ignore"]` | `ref_modele="REF"` (BBB ignoré) |
| T1.7 | PDF 3 col (format principal), pas de mapping | `["R","C","D"]`, `column_mapping=None` | identique à T1.3 selon `third_column_choice` |

### 8.2 Tests Phase 2 — Interface

| # | Scénario | Action | Résultat attendu |
|---|---|---|---|
| T2.1 | Ouvrir dialogue avec CSV 2 col | Observer | Widget mapping pré-rempli : col0→ref_modele, col1→commercial_ref |
| T2.2 | Ouvrir dialogue avec PDF 3 col | Observer | Mapping pré-rempli conforme au format PDF |
| T2.3 | Format non reconnu | Déposer fichier | Bandeau rouge + widget mapping déplié + bouton Importer désactivé |
| T2.4 | Format non reconnu, mapper ref_modele | Sélectionner ref_modele dans combo | Bouton Importer activé + bandeau orange |
| T2.5 | Format reconnu, replier mapping | Cliquer chevron | Widget replié, import fonctionne normalement |
| T2.6 | Format reconnu, modifier mapping puis importer | Swap col0↔col1 | Import utilise le mapping modifié |
| T2.7 | Import PDF 3 col sans toucher au mapping | Importer | Données identiques à avant la feature |

### 8.3 Tests Phase 3 — End-to-end avec fichiers réels

| # | Fichier test | Validation |
|---|---|---|
| T3.1 | PDF fournisseur habituel (3 col) | Vérifier 5 enregistrements en DB = valeurs attendues |
| T3.2 | CSV 2 col standard | Vérifier ref_modele + commercial_ref corrects |
| T3.3 | CSV ordre inversé (commercial en col0) | Mapper manuellement, vérifier import correct |
| T3.4 | CSV 5 col avec champs supplémentaires | Mapper les 4 pertinents, ignorer le 5ème |

---

## 9. Savepoints et rollback

| Savepoint | Tag git | Description |
|---|---|---|
| Avant démarrage | `v3.29.2` (actuel) | État stable actuel — rollback ici si blocage |
| Fin Phase 1 | `v3.29.3` | Infrastructure seule, flag désactivé |
| Fin Phase 2 | `v3.29.4` | Widget intégré, flag désactivé |
| Release | `v3.30.0` | Flag activé, feature complète |

**Procédure de rollback :**
```bash
git checkout v3.29.2   # retour immédiat à l'état stable
# OU désactiver le flag sans rollback :
# Config.ENABLE_COLUMN_MAPPING = False
```

---

## 10. Fichiers modifiés (périmètre)

| Fichier | Modifications |
|---|---|
| `src/core/config.py` | + `ENABLE_COLUMN_MAPPING = False` |
| `src/core/import_manager.py` | + `MappingWidget`, `column_mapping` dans config, `_parse_row_data()` branching, `_validate_and_accept()` lecture mapping |
| `src/core/constants.py` | + constantes libellés champs mapping (optionnel) |
| `CHANGELOG.md` | Entrée v3.29.3, v3.29.4, v3.30.0 |
| `README.md` | Version + section Import |

**Fichiers NON modifiés :**
- `src/data/database_manager.py` — aucun changement DB
- `src/ui/*` — aucun impact sur l'interface principale
- Toute logique d'import post-dialogue (`_execute_import`, `_import_single_file`, etc.) — **inchangée**

---

*CDC rédigé le 2026-03-16 — à maintenir au fil des phases*
