# Instructions projet — 1001pieces_autofill

## Règles absolues
- **ZERO REGRESSION** : toujours vérifier le bon fonctionnement après un refacto ou un déplacement de code.
- Ne pas modifier le code sauf si explicitement demandé.
- Langue : français pour les commentaires, messages utilisateur et noms de variables métier.

## Architecture
- Point d'entrée : `run.py` → `src/ui/main_refactored.py::main()`
- Base de données : `data/appareils.db` (SQLite, 598k+ enregistrements)
- Logs : `data/logs/` (créé automatiquement au premier lancement)
- Fichiers PDF de test : `tests/fixtures/pdf_samples/`

## Conventions
- Tous les services héritent de `BaseService` (`src/services/`)
- Les dialogues utilisent `show()` + callbacks — jamais `exec_()` (évite le freeze macOS)
- La sauvegarde passe toujours par `EventDrivenSaveService`, jamais directement sur le DB manager
- Les constantes sont centralisées dans `src/core/constants.py`

## Flags de configuration clés (`src/core/config.py`)
- `Config.USE_FTS5 = True` — index FTS5 trigram actif
- `Config.SEARCH_PIECES_ONLY = True` — recherche sur `pieces.ref_piece` uniquement (désactive FTS5)

## Supersession (v3.26.0)
- Table `piece_supersessions(ref_old PK, ref_new)` + `pieces.is_obsolete`
- Résolution de chaîne via CTE récursive SQL (`get_supersession_chain`, `get_all_predecessors`)
- Bannière bidirectionnelle dans `table_controller.py` (modes `superseded` / `replacing`)
- CDC complet : `docs/cdc_supersession_pieces.md`

## Outils
- GitHub CLI : `~/bin/gh`
- Lancement app : `python3 run.py` ou double-clic `1001pieces_autofill.command`
- Rebuild index FTS5 : menu Gestion → "Index de recherche FTS5" → "Construire l'index"
