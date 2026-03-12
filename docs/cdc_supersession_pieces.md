# Cahier des charges — Gestion de la supersession de références pièces

**Statut :** En conception
**Version :** 0.2
**Contexte :** L'application gère la compatibilité entre pièces détachées et appareils électroménagers. Les fabricants remplacent régulièrement une référence par une nouvelle (supersession). Ce document définit les règles métier, le modèle de données et les comportements attendus pour gérer ces évolutions.

---

## 1. Objectifs

- Tracer explicitement qu'une référence pièce A a été remplacée par une référence B
- Permettre la recherche par ancienne référence (remontée automatique vers la ref courante)
- Gérer les pièces obsolètes sans successeur
- Conserver **toutes** les références (aucune suppression, aucune migration des associations)
- Supporter la saisie manuelle et l'import depuis un fichier fournisseur

---

## 2. Modèle de données

### 2.1 Nouvelle table `piece_supersessions`

```sql
CREATE TABLE piece_supersessions (
    ref_old  TEXT NOT NULL,
    ref_new  TEXT,           -- NULL si pièce obsolète sans remplacement
    PRIMARY KEY (ref_old),
    FOREIGN KEY (ref_old) REFERENCES pieces(ref_piece),
    FOREIGN KEY (ref_new) REFERENCES pieces(ref_piece)
);
```

### 2.2 Règles de la table

| Cas                        | `ref_old`     | `ref_new`     |
|----------------------------|---------------|---------------|
| Supersession normale       | ancienne ref  | nouvelle ref  |
| Pièce obsolète             | ref obsolète  | NULL          |

### 2.3 Schéma existant — aucune modification

- Table `pieces` : inchangée
- Table `associations` (lien pièce ↔ appareil) : inchangée
- Les associations restent liées à leur `ref_piece` d'origine

---

## 3. Règles métier

### 3.1 Chaînes de succession

Une chaîne peut être longue : `A → B → C → D (courante)`

- La ref **courante** est celle qui n'apparaît pas dans `ref_old` (ou dont `ref_new` est NULL mais qui n'est pas obsolète)
- Une ref peut n'être que dans `ref_new` (jamais remplacée = courante)
- Une ref peut être à la fois dans `ref_new` d'une entrée et dans `ref_old` d'une autre (nœud intermédiaire)

### 3.2 Relations

- **1-to-1** : cas standard. Une ancienne ref → une nouvelle ref.
- **1-to-N** (rare) : une ref se divise en plusieurs nouvelles. Modélisé par N entrées avec le même `ref_old`.
- **N-to-1** : plusieurs anciennes refs convergent vers une seule. Modélisé par N entrées avec le même `ref_new`.

### 3.3 Statuts d'une référence

| Statut       | Condition                                                                              |
|--------------|----------------------------------------------------------------------------------------|
| **Courante** | Absente de `ref_old`, ou présente mais `ref_new` non nulle ET elle-même non remplacée |
| **Remplacée**| Présente dans `ref_old` avec `ref_new` non null                                       |
| **Obsolète** | Présente dans `ref_old` avec `ref_new` = NULL                                         |

### 3.4 Intégrité

- Interdire les cycles (`A → B → A`)
- Interdire qu'une ref pointe vers elle-même (`ref_old = ref_new`)
- Une ref ne peut avoir qu'**une seule** entrée dans `ref_old` (PRIMARY KEY)

---

## 4. Comportement de la recherche

### 4.1 Recherche par référence exacte ou partielle

Quand l'utilisateur recherche une ref (ex: `REF123`) :

1. Chercher `REF123` dans `pieces` normalement
2. **En parallèle**, chercher `REF123` dans `piece_supersessions.ref_old`
3. Si trouvé, remonter la chaîne jusqu'à la ref courante (CTE récursive SQL)
4. Retourner les résultats de la **ref courante** (ses associations avec les appareils)
5. Afficher une mention visible : `REF123 → REF456 → REF789 (courante)`

### 4.2 Indexation FTS5

**Décision architecturale (Case B) :** L'index FTS5 (`appareils_fts`) couvre uniquement les colonnes d'`appareils`. Le mode `SEARCH_PIECES_ONLY=True` (production) court-circuite FTS5 entièrement et effectue une recherche LIKE sur `pieces.ref_piece`. La table `piece_supersessions` étant petite (quelques dizaines d'entrées), une requête LIKE dessus est sub-milliseconde — créer un index FTS5 séparé n'apporte aucun gain mesurable. La résolution de la chaîne de succession se fait en Python via `_resolve_refs_via_supersession()` avant la construction de la condition SQL.

### 4.3 Affichage dans les résultats

Pour chaque pièce affichée dans les résultats de recherche :
- Si la ref recherchée est une ancienne ref : indicateur discret dans la colonne `ref_piece` (ex: `REF123 →`)
- Le chemin complet de succession en tooltip au survol
- Si obsolète : mention `⚠️` avec tooltip "Obsolète — aucun remplacement"

### 4.4 Recherche avancée `||`

Le comportement existant (recherche OR sur plusieurs refs) est **conservé et étendu** :
- Chaque terme du `||` déclenche la remontée de chaîne si applicable
- Ex: `REF123 || REF456` → cherche REF123 (+ ses successeurs) ET REF456 (+ ses successeurs)

---

## 5. Interface utilisateur

### 5.1 Gestionnaire de pièces — section "Succession"

Dans la fiche d'une pièce :
- Afficher le statut : `Courante` / `Remplacée par REF456` / `⚠️ Obsolète`
- Afficher la chaîne complète en lecture : `REF001 → REF002 → REF003 (vous êtes ici)`
- Bouton **"Marquer comme remplacée par"** → saisie de la nouvelle ref
- Bouton **"Marquer comme obsolète"** → confirmation requise
- Bouton **"Annuler la supersession"** → supprime l'entrée dans `piece_supersessions`

### 5.2 Indicateurs visuels dans le tableau principal

Indicateur **discret** dans la colonne `ref_piece` (pas de colonne dédiée) :

| Indicateur | Signification             |
|------------|---------------------------|
| `REF →`    | Ref remplacée (tooltip : chaîne complète) |
| `REF ⚠️`   | Ref obsolète (tooltip : "Aucun remplacement") |
| `REF`      | Ref courante (pas d'indicateur) |

### 5.3 Notifications — pièces obsolètes

Si une pièce associée à un appareil est marquée obsolète, l'utilisateur est alerté :
- Au moment où la pièce est marquée obsolète : dialogue de confirmation listant les appareils concernés
- Indicateur persistant dans le tableau des appareils (même logique que §5.2)

### 5.4 Historique

Chaque ajout/modification/suppression de supersession est tracé dans le panneau historique de l'app (type `PIC`).

---

## 6. Import

> **Contexte** : chaque fichier importé (CSV / PDF) contient une liste d'appareils compatibles avec **une seule référence pièce**. La ref est déclarée dans le dialogue d'import, pas dans le fichier. La succession se configure donc uniquement au niveau du dialogue.

### 6.1 Import fichier unique — déclaration de succession avec la base existante

Lors de l'import d'un fichier contenant **une seule référence**, le dialogue d'import propose une section optionnelle "Succession" avec deux champs en autocomplétion sur les références déjà présentes en base :

```
┌─ Succession (optionnel) ──────────────────────────────────────┐
│  Cette référence remplace      : [ REF123 ▾ ]  ← autocomplétion
│  Cette référence est remplacée : [ REF456 ▾ ]  ← autocomplétion
└───────────────────────────────────────────────────────────────┘
```

Comportement selon le champ renseigné :

| Champ renseigné                    | Entrée créée dans `piece_supersessions`              |
|------------------------------------|------------------------------------------------------|
| "Cette ref remplace REF123"        | `(ref_old=REF123, ref_new=ref_importée)`             |
| "Cette ref est remplacée par REF456" | `(ref_old=ref_importée, ref_new=REF456)`           |
| Les deux renseignés                | Les deux entrées créées (ref_importée = nœud intermédiaire) |
| Aucun renseigné                    | Aucune entrée de succession (comportement actuel)    |

Règles :
- L'autocomplétion interroge la table `pieces` existante (recherche partielle sur `ref_piece`)
- Les deux champs sont indépendants et facultatifs
- Si les deux sont renseignés, la cohérence de chaîne est vérifiée (pas de cycle)
- Le champ "remplacée par" ne peut pas pointer vers la même ref que "remplace" (évite A → A)

### 6.2 Import multi-fichiers — sélection de la ref courante (topologie étoile)

Quand un fichier contient plusieurs refs pour la même pièce **sans colonne `ref_remplace`**, le dialogue d'import propose une étape dédiée :

```
Refs détectées pour cette pièce :
  ○ REF123   ○ REF456   ● REF789  ← Ref courante (bouton radio)

  Aperçu :  REF123 → REF789
             REF456 → REF789
```

- Un **bouton radio** désigne la ref courante (choix exclusif)
- Les autres refs pointent toutes directement vers elle (topologie en étoile, pas de chaîne forcée)
- L'aperçu se met à jour en temps réel

Cette approche est préférable à une case à cocher car elle impose un choix unique et prévisualise le résultat avant validation.

### 6.3 Saisie manuelle

Via le gestionnaire de pièces (cf. §5.1) ou via un écran dédié "Gérer les successions" accessible depuis le menu Gestion.

---

## 7. Cas limites à traiter

| Cas                                       | Comportement attendu                                                  |
|-------------------------------------------|-----------------------------------------------------------------------|
| Cycle détecté (`A → B → A`)               | Refus avec message d'erreur explicite                                 |
| Ref inexistante dans `pieces`             | Créer la ref automatiquement (ref "fantôme" sans associations)        |
| Chaîne très longue (> 10 nœuds)           | Remontée jusqu'à la ref courante, affichage tronqué avec "…"         |
| 1-to-N (split rare)                       | Afficher les N successeurs, laisser l'utilisateur choisir            |
| Suppression d'une ref intermédiaire       | Bloquer si elle a des successeurs ; proposer de rechaîner             |
| Import d'une supersession déjà existante  | `INSERT OR REPLACE` — mise à jour silencieuse                        |
| Pièce obsolète associée à un appareil     | Alerte utilisateur avec liste des appareils concernés                |

---

## 8. Décisions arrêtées

| Sujet                          | Décision                                                                 |
|-------------------------------|--------------------------------------------------------------------------|
| FTS5                          | ✅ Pas d'indexation séparée — `piece_supersessions` est petite, LIKE sub-ms. Résolution chaîne en Python avant SQL. |
| Affichage tableau principal   | ✅ Indicateur discret dans la colonne `ref_piece` (pas de colonne dédiée) |
| Export CSV/HTML               | ✅ Inchangé — le statut de succession n'est pas exporté                  |
| Notification obsolescence     | ✅ Alerte au moment du marquage + indicateur persistant                  |
| Performance chaînes longues   | ✅ CTE récursive SQL (`WITH RECURSIVE`) pour la remontée de chaîne       |
| UX import multi-refs          | ✅ Bouton radio "Ref courante" + aperçu temps réel (topologie étoile)   |

---

## 9. Dépendances techniques

- `database_manager.py` : nouvelles méthodes `get_supersession_chain(ref)`, `resolve_current_ref(ref)`, `add_supersession(ref_old, ref_new)`, `_resolve_refs_via_supersession(term)` (résolution chaîne avant SQL — pas de rebuild FTS5)
- `search_service.py` : étendre la résolution de recherche pour remonter la chaîne avant d'interroger les associations
- `import_manager.py` : UI dialogue — champs autocomplétés (fichier unique) + bouton radio sélection ref courante (multi-fichiers)
- `pieces_manager.py` / `piece_management_service.py` : UI de gestion des successions, notifications obsolescence
- Migration DB : `CREATE TABLE piece_supersessions` + ajout colonne `pieces.is_obsolete` — versionné dans `_setup_supersession_table()`

---

*Document évolutif — à mettre à jour au fil des décisions de conception.*
