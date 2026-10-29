# 1001pieces_autofill — Gestionnaire d'Appareils

Application de gestion de pièces détachées et d'appareils électroménagers : import de catalogues fournisseurs (PDF, CSV, collage), complétion assistée des fiches, relations entre références (succession, équivalences) et exports pour le site (CSV, HTML, métas SEO, titres de fiche produit).
Interface PyQt5, base SQLite conçue pour des centaines de milliers d'appareils.

La version courante est affichée dans la barre d'état de l'application et définie par `Config.VERSION` (`src/core/config.py`). L'historique détaillé est dans [CHANGELOG.md](CHANGELOG.md) ; le guide d'utilisation (`docs/guide_utilisation.html`) liste les nouveautés côté utilisateur.

## Lancement

```bash
# Double-clic (sans terminal)
./1001pieces_autofill.command

# Ligne de commande
python3 run.py
```

## Installation

```bash
pip3 install -r requirements.txt
# PyQt5 >= 5.15, camelot-py[cv] (PDF), qtawesome >= 1.3 (icônes)
```

### Installer sur un autre poste (Windows ou macOS)

Configuration → Exporter l'application… (ou `python3 export_app.py --cible windows|macos`)
produit une archive `.zip` : code, base la plus récente, guide, fichiers de test d'import.
Windows : version portable (Python inclus, rien à installer), dézipper puis `1001pieces_autofill.bat`.
Détail dans le guide d'utilisation, section « Installer l'application sur un autre poste ».

## Fonctionnalités

### Import
- **PDF** (Camelot), **CSV** (délimiteur détecté), **collage** depuis Excel, **glisser-déposer** de plusieurs fichiers
- **Import non bloquant** — analyse et écriture SQLite hors du fil principal
- **Mapping de colonnes** — correspondance colonnes du fichier → champs de la base, en-têtes reconnus
- **Relations déclarées à l'import** — « remplace » / « remplacée par » / équivalences, plusieurs références possibles ; à l'import de plusieurs fichiers, une carte par fichier, arbre des remplacements et désignation de la référence courante
- **Complétion automatique** — l'import complète aussi les appareils existants restés vides

### Suggestions et complétion assistée
- **Suggestions de Type / Fabricant** par similarité de références, d'après la pièce importée, la lignée de la pièce et la colonne « Autre référence »
- **Bouton « Suggestions à valider (N) »** — fenêtres de revue à 3 états (validée, refusée, en attente), refus mémorisés
- **Auto-complétions tracées** — affichées en italique, fenêtre « Auto-complétés à vérifier », bouton « Tout valider », Espace coche / décoche partout
- **Orthographe alignée** — casse des marques et des types ramenée à celle déjà présente en base

### Recherche
- **Recherche sur les références pièces** (`SEARCH_PIECES_ONLY = True`), recherche exacte, opérateurs `&&` (ET) et `||` (OU)
- **Index FTS5 trigram** construit à la demande (menu Gestion → Index de recherche FTS5)
- **Bannières de supersession** — « ancienne réf. : A → B (courante) » et « REF remplace : A, B », avec bascule pour inclure ou exclure les références liées
- **Filtres Type / Marque** avec liste complète et remise à zéro

### Pièces et relations
- **Succession** — table `piece_supersessions(ref_old, ref_new)`, chaînes résolues par CTE récursive ; cahier des charges : `docs/cdc_supersession_pieces.md`
- **Équivalences** — groupes symétriques, rattachés à une lignée, équivalentes hors chaîne
- **Obsolescence** — `pieces.is_obsolete`, indépendante de la succession
- **Libellés de pièces** recopiés sur toute la famille d'une pièce ; pièces communes par lignée
- **Gestionnaire de pièces** — édition, chips de références, sélecteur avec recherche en temps réel, références fantômes
- **Intégrité** — clés étrangères SQLite activées (`Config.FOREIGN_KEYS`)

### Export
- **Boutons Titre, HTML Marques, HTML Détails, Exporter CSV** — l'export suit exactement ce qu'affichent le tableau et la bannière active
- **Titre de fiche produit** — libellé, types, marques, référence la plus récente, selon des gabarits réglables
- **Gabarits** — menus triés, filtre à la saisie et 3 derniers choix (« Récents ») à partir de 6 gabarits
- **HTML configurable** — modèles, séparateurs, codes englobants, aperçu en temps réel
- **Métas SEO** générées
- **Configuration persistante** — `data/export_config.json` (propre au poste), dossier de sortie réglable (Outils → Configuration des exports…)

### Interface et sûreté
- **Pagination virtuelle stable** — 100 lignes affichées, défilement infini, navigation vers les cellules incomplètes
- **Sauvegarde événementielle** (`EventDrivenSaveService`) et sauvegardes de la base en rotation, restauration intégrée
- **Annuler / Rétablir**, historique structuré (rechargé au lancement, alertes surlignées)
- **Doublons** — détection visuelle et fusion
- **Poignée de recopie** — double-clic vers le bas ou vers le haut
- **Dialogues non bloquants** (`show()` + callbacks), icônes qtawesome, styles centralisés (`StyleManager`)

## Raccourcis clavier

Sous Windows : Ctrl à la place de Cmd. Liste complète dans le guide d'utilisation.

| Raccourci | Action |
|-----------|--------|
| Double-clic / F2 | Modifier la cellule |
| Cmd+N | Nouvelle ligne |
| Cmd+Z / Cmd+Y | Annuler / Rétablir |
| Cmd+C / Cmd+V | Copier / Coller (compatible Excel) |
| Cmd+S | Sauvegarder |
| Cmd+D | Valeurs existantes de la colonne |
| Suppr | Vider les cellules sélectionnées |
| Cmd+↑ / Cmd+↓ | Cellule vide précédente / suivante |
| Cmd+Espace / Maj+Espace | Sélectionner la colonne / la ligne |
| Espace | Cocher / décocher dans les fenêtres à cases |
| Cmd+F / Échap | Aller à la recherche / L'effacer |
| Cmd+Maj+L | Modifier le libellé de la pièce recherchée |
| F5 | Actualiser |
| F12 | Visualiseur de logs |

## Structure du projet

```
1001pieces_autofill/
├── run.py                        # Point d'entrée → src/ui/main_refactored.py::main()
├── 1001pieces_autofill.command   # Lanceur macOS (+ 1001pieces_autofill.app)
├── export_app.py                 # Export de l'application vers un autre poste
├── requirements.txt
├── CHANGELOG.md
│
├── src/
│   ├── core/       # config.py (VERSION, flags), constants.py, logger.py, import_manager.py
│   ├── data/       # database_manager.py (+ _db_mixins/), modèle de table, validation, extraction PDF
│   ├── services/   # ~40 services métier (héritent de BaseService) : sauvegarde, import,
│   │               # recherche, suggestions, exports, sauvegardes/restauration, historique…
│   ├── ui/         # fenêtre principale, contrôleur de tableau, gestionnaire de pièces,
│   │               # fenêtres de revue, configuration des exports, titres, menus de gabarits…
│   └── utils/      # texte, SEO, générateur de titres, gestion d'erreurs
│
├── data/
│   ├── appareils.db              # Base SQLite (non suivie par git)
│   ├── export_config.example.json # Modèle de configuration des exports (export_config.json, local, non suivi)
│   └── logs/                     # Créé au premier lancement
│
├── docs/
│   ├── guide_utilisation.html    # Guide utilisateur (à jour à chaque évolution)
│   ├── synthese_projet.html/.pdf
│   ├── cdc_supersession_pieces.md, cdc_column_mapping_import.md
│   └── IMPROVEMENTS.md, MIGRATION_QTABLEVIEW.md
│
├── scripts/        # icône, scripts de maintenance de la base, CI
└── tests/          # tests unitaires (pytest) + fixtures (PDF d'exemple)
```

## Tests

```bash
QT_QPA_PLATFORM=offscreen python3 -m pytest tests/
```

Nécessite PyQt5 et pytest dans l'interpréteur utilisé. Un workflow GitHub Actions valide l'export Windows.

## Configuration clé (`src/core/config.py`)

```python
Config.USE_FTS5 = True             # Index plein-texte FTS5
Config.SEARCH_PIECES_ONLY = True   # Recherche uniquement sur les refs pièces (prend le pas sur FTS5)
Config.FOREIGN_KEYS = True         # Clés étrangères SQLite
```

Construction de l'index FTS5 : menu **Gestion → Index de recherche FTS5 → Construire l'index**.
