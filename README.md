# 1001pieces_autofill — Gestionnaire d'Appareils

Application de gestion de pièces détachées et d'appareils électroménagers. Interface PyQt5, base SQLite de 598 000+ enregistrements, recherche plein-texte FTS5, gestion de la supersession de références. **v3.26.0**

## Lancement

```bash
# Double-clic (sans terminal)
./1001pieces_autofill.command

# Ligne de commande
python3 run.py
```

## Structure du projet

```
1001pieces_autofill/
├── run.py                        # Point d'entrée
├── 1001pieces_autofill.command   # Lanceur macOS
├── requirements.txt              # Dépendances (PyQt5, Camelot-py)
├── CHANGELOG.md                  # Historique des versions
│
├── src/
│   ├── core/
│   │   ├── config.py             # Configuration globale (VERSION, flags)
│   │   ├── constants.py          # Constantes UI et DB
│   │   ├── logger.py             # Système de logs
│   │   └── import_manager.py     # Dialogue d'import (CSV/PDF) avec lazy loading
│   │
│   ├── data/
│   │   ├── database_manager.py   # Requêtes SQLite, FTS5, supersession, cache
│   │   ├── data_validator.py     # Validation des données
│   │   ├── data_exporter.py      # Exports CSV/HTML
│   │   └── pdf_extractor_camelot.py
│   │
│   ├── services/                 # ~30 services métier
│   │   ├── event_bus.py          # Bus d'événements interne
│   │   ├── event_driven_save_service.py  # Sauvegarde <100ms
│   │   ├── search_cache_service.py
│   │   ├── drag_handle_service.py
│   │   ├── grouped_history_service.py
│   │   └── ...
│   │
│   ├── ui/
│   │   ├── main_refactored.py    # Fenêtre principale (QMainWindow)
│   │   ├── table_controller.py   # Pagination, tri, recherche, bannière supersession
│   │   ├── pieces_manager.py     # Gestionnaire de pièces + succession
│   │   ├── piece_management_service.py
│   │   ├── pieces_panel_service.py
│   │   └── ...
│   │
│   └── utils/
│       ├── text_utils.py
│       ├── error_handler.py
│       └── seo_generator.py
│
├── data/
│   └── appareils.db              # Base SQLite (~598 000 enregistrements)
│
└── docs/
    ├── cdc_supersession_pieces.md   # Cahier des charges supersession (v1.0)
    ├── IMPROVEMENTS.md              # Améliorations futures
    └── MIGRATION_QTABLEVIEW.md      # Historique migration QTableView (v3.17)
```

## Fonctionnalités

### Base de données
- **598 000+ enregistrements** — pagination virtuelle (100 lignes affichées, scroll infini)
- **FTS5 trigram** — index plein-texte sur toutes les colonnes appareils (`USE_FTS5=True`)
- **Sauvegarde événementielle** — latence <100ms (EventDrivenSaveService)
- **Cache adaptatif** — invalidation sélective après modification/import

### Recherche
- **Recherche pièces uniquement** (`SEARCH_PIECES_ONLY=True`) — filtre sur `pieces.ref_piece`
- **Opérateurs avancés** — `&&` (ET), `||` (OU)
- **Supersession** — résolution automatique de la chaîne de succession :
  - Bannière "ancienne réf. : A → B (courante)" avec toggle pour voir A seul
  - Bannière "REF remplace : A, B" avec toggle pour inclure les appareils des réfs remplacées

### Gestion des pièces et supersession
- **Succession** — `piece_supersessions(ref_old PK, ref_new NOT NULL)` — CTE récursive pour chaînes longues
- **Obsolescence** — colonne `pieces.is_obsolete` indépendante de la succession
- **Indicateurs visuels** — `→` (remplacée) et `⚠` (obsolète) dans toutes les listes de pièces
- **Alerte obsolescence** — dialogue listant les appareils concernés avant marquage
- **Import avec succession** — déclaration directe dans le dialogue d'import (champs autocompletés)

### Import
- **PDF** — extraction Camelot-Py avec lazy loading (0 freeze)
- **CSV** — détection automatique délimiteur et format
- **Drag & Drop** — multi-fichiers simultané
- **Succession à l'import** — "cette réf. remplace" / "remplacée par" + radio "Courante" multi-fichiers

### Interface
- **Historique structuré** — badges colorés MOD/IMP/EXP/SUP/ANN/PIC/SYS, agrégation `×N appareils`
- **Dialogues non-bloquants** — `show()` + callbacks (Finder ne freeze plus)
- **Undo/Redo** — historique d'actions annulables
- **Doublons** — détection visuelle + interface hiérarchique de fusion
- **Drag handle** — duplication vers le bas par double-clic

## Installation

```bash
pip3 install -r requirements.txt
# PyQt5>=5.15.0 + camelot-py[cv] pour les PDF
```

## Raccourcis clavier

| Raccourci | Action |
|-----------|--------|
| Cmd+N | Nouvelle ligne |
| Cmd+Z / Cmd+Y | Annuler / Refaire |
| Cmd+F | Recherche |
| Cmd+D | Auto-complétion (Type/Fabricant) |
| Cmd+↑/↓ | Navigation cellules vides |
| Échap | Réinitialiser recherche/filtres |
| F5 | Actualiser |
| F12 | Visualiseur de logs |
| Delete | Effacement cellule |

## Performances (v3.14+)

| Opération | Avant | Après |
|-----------|-------|-------|
| Requêtes SQL | 2 300ms | 150ms |
| Sauvegarde | 5 000ms | <100ms |
| Import PDF (freeze) | 15s | 0s |
| Effacement recherche | 2 500ms | ~6ms |

## Configuration clé (`src/core/config.py`)

```python
Config.USE_FTS5 = True             # Index plein-texte FTS5 (désactiver si index non construit)
Config.SEARCH_PIECES_ONLY = True   # Recherche uniquement sur les refs pièces
```

Reconstruction index FTS5 : menu **Gestion → Index de recherche FTS5 → Construire l'index** (~5s)

---

Voir [CHANGELOG.md](CHANGELOG.md) pour l'historique complet des versions.
