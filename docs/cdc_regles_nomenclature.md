# Cahier des charges — Règles de nomenclature des appareils (types justes)

**Statut :** lots 1 et 2 appliqués ; lot 3 (moteur sans écran) mergé, tables remplies en production ; lot 4 (écran Règles + revue) codé
**Version :** 0.5 (2026-11-23) — lot 4 : écran Règles, revue des propositions, acceptations annulables
**Contexte :** Le client veut que ses clients retrouvent leur appareil par une recherche, sous la bonne marque et le bon type. Les fabricants codent le type dans leurs références (BSH : `S…` = lave-vaisselle ; Electrolux : PNC `911…` = lave-vaisselle ; Neff : `C17M…` = four combiné micro-ondes). Ce document définit comment l'outil apprend, fait valider et applique ces **règles de nomenclature** pour corriger et compléter le type des appareils.

---

## 0. Décisions client (2026-11-23)

| # | Décision |
|---|---|
| D1 | **Pas d'attributs.** La base du site n'en a pas : chaque appareil a **un seul type**, choisi dans une liste fermée. |
| D2 | Les combinés restent des **types à part entière** (« Four vapeur » reste un type). |
| D3 | Création d'un **nouveau type « Four combiné micro-ondes »** (nom confirmé le 2026-11-23, voir D6), sur le modèle de « Four vapeur ». |
| D4 | Toute correction passe par une **validation humaine** (une règle validée = des centaines d'appareils) ; aucune correction silencieuse. |
| D5 | En cas de doute, on cherche des réponses **hors de l'application** (fiches fabricants, notices) et on garde la source. |
| D6 | Libellé exact du nouveau type : **« Four combiné micro-ondes »** (à créer à l'identique côté site). |
| D7 | Règles trouvées par l'analyse des données **sans source web** : **validées d'office si pureté ≥ 98 % ET un 2e signal d'accord** (vote des pièces > 60 % ou 2e clé) ; sinon **une par une**. |
| D8 | **Acceptation groupée** des propositions **fortes** d'une même règle : **oui, avec récapitulatif** (nombre d'appareils, comptage par type avant/après) et une entrée d'historique annulable. Les propositions simples restent ligne à ligne. |
| D9 | Types **accessoires** (Accessoires, Porte, Tiroir à couverts, Filtre à eau, Kit d'évacuation, Panier à couverts, Filtre, Rails téléscopique, Kit de recyclage) : **exclus des règles** — aucune règle ne propose ni ne retire ces types ; chantier séparé. |
| D10 | Lot 2 : liste **figée famille par famille** le 2026-11-23 (§ 4.1) — **6 104 appareils**, élargie au-delà de l'estimation (ancienne génération BSH, AEG KMX/CM/NKM/NKO, Electrolux EVY/EVL/EVM/EVK, Bosch HMG8601/8621/8701/8721) ; Whirlpool `AMW` **reste Micro-ondes** (vendu comme micro-ondes) ; `types_autorises` (§ 3) reporté au **lot 3**. |
| D11 | Lot 3 : `types_autorises` dans **`data/types_autorises.json`, versionné** (`data/export_config.json` est propre à chaque poste, gitignoré) : la changer = une PR, après création du type sur le site. |
| D13 | Lot 4 : **acceptation groupée** permise pour les propositions **fortes** (D8) **et pour les simples d'une règle validée sur source web** (origine `web` + `source_url`) — cas Gaggenau `BS*` : 767 simples (Four → Four vapeur, types voisins) que l'on n'accepte pas une par une. Les autres simples restent une par une ; le refus groupé est toujours permis. |
| D14 | Lot 4 : l'écran est dans le menu **Données** (« Règles de nomenclature… ») : il n'existe pas de menu Gestion. |
| D15 | Lot 4 : « Chercher de nouvelles règles » **enregistre toutes les candidates** en statut `proposee` (≈ 7 400 sur la base réelle) ; l'écran filtre alors par défaut sur « changeraient des appareils » (≈ 610). Les autres serviront au typage à l'import (lot 5). |
| D16 | Lot 4 : **D7 ne s'applique pas tout seul** : l'écran signale les règles de pureté ≥ 98 % (filtre et mention « D7 » sur la fiche, le 2e signal se lit dans les exemples) ; on les valide par sélection multiple, après un récapitulatif (D4). |
| D12 | Lot 3, catalogue § 9.2 tranché famille par famille : Gaggenau **`BS*` → Four vapeur** (BSP série 200 et BS4 série 400 = combi-vapeur) ; Bauknecht `EM*` = **zone grise** ; Liebherr `G*` Congélateur, `GK*` Réfrigérateur + exceptions `GKN[12]*` Congélateur, `GDC*` Réfrigérateur ; **pas de règle** `HMG8601/8621/8701/8721` (décision ponctuelle du lot 2) ; Whirlpool `AKR[4-9]*` Hotte, `AKR3*` Plaque, `AGB*` Lave-vaisselle ; Beko `FSE[56]*`/`CSE[56]*` Cuisinière, `CSE3*` Réfrigérateur, `FSE2*` Congélateur ; AEG `KMF*` → Four combiné micro-ondes ; Electrolux `EW?D*` Sèche-linge ; validées une par une : Candy, Bosch `HBC??D*`, Siemens `CI??W*`, De Dietrich `DOV*`, Hotpoint `AQD*`/`AQM*`. |

---

## 1. Objectifs et hors périmètre

**Objectifs**
- Corriger les types faux, en priorité ceux qui égarent un client (four classique affiché « Four vapeur »).
- Typer automatiquement les appareils importés quand une règle validée s'applique.
- Rendre chaque règle **justifiable** : exemples, couverture, source web.

**Hors périmètre**
- Attributs (nettoyage, encastrable…) — exclus par D1.
- Correction des **marques** : le bilan (§ 2.3) n'a trouvé aucune erreur de marque ; seuls deux ménages ponctuels sont listés en § 10.
- Modification de la recherche elle-même.

---

## 2. Constat chiffré (mesures du 2026-11-23, base de 720 420 appareils, lecture seule)

### 2.1 Les règles existent et tiennent

- Règle « préfixe le plus long, pur à ≥ 90 %, ≥ 5 appareils », marque puis groupe, sur deux clés (nom commercial et code usine numérique) : **98,3 % des appareils couverts, 99,5 % d'accord** avec le type en base.
- 3 370 désaccords, dont 368 « forts » (nom commercial et code usine d'accord entre eux).

### 2.2 Ce que valent les désaccords (arbitrés par les pièces et le libellé d'origine)

| Catégorie | Lignes | Leçon |
|---|---|---|
| Accessoires (DHZ, SMZ…) | 108 | sous-familles légitimes |
| Règle trop large, démentie par les pièces | 995 | préfixes de 1-2 car., préfixes numériques courts, règles de groupe appliquées à une marque voisine |
| Types voisins (froid / cuisson / linge) | 1 532 | les pièces ne départagent pas → règles **par position** |
| Four / Four vapeur | 253 | zone polluée (§ 2.4) |
| Indécidables | 391 | revue humaine ou source web |
| Erreurs probables | 91 | ~20 sûres après vérification (§ 9.1) |

Types voisins : sur 231 préfixes mélangés (86 917 appareils), **123 (54 254 appareils) sont départagés à ≥ 95 %** par un caractère à une position donnée (validation croisée moitié/moitié). Les règles « contient tel caractère » sont fragiles (`AWE8230ZEN` contient un Z par hasard) : à proscrire.

### 2.3 Marques

Pas d'erreur de marque détectée : un même code usine sous deux marques = sous-traitance (Ikea porte 2 760 codes Whirlpool et 1 155 PNC Electrolux). Doublons (marque, réf. modèle) = variantes commerciales (Miele `G 686` / `G 686 SC`).

### 2.4 Le piège à retenir : l'erreur systématique

Les listes Whirlpool portent le libellé « Four Vapeur » sur toute la gamme four. Résultat : **1 891 appareils `AKP`/`AKZ` (Whirlpool et marques sœurs) typés « Four vapeur »** alors que ce sont des fours multifonction sans vapeur, et les vrais fours vapeur `AKZ9S…` typés « Four ». Sur `AKP`, la **majorité est fausse** : une règle apprise sur les données seules reproduirait l'erreur. D'où D4 et D5.

---

## 3. Liste fermée des types

Aujourd'hui la liste des types est lue en base (`SELECT DISTINCT type`, `Config` requête `distinct_types`) : n'importe quelle faute de frappe crée un type.

- Nouvelle liste **`types_autorises`** : `data/types_autorises.json`, **versionné** (D11), lu par `src/utils/types_autorises.py` ; initialisée le 2026-11-23 avec les **44 types présents en base** (dont « Four combiné micro-ondes », créé au lot 2).
- Une règle ne peut produire qu'un type de cette liste, jamais un type accessoire (D9) : contrôle à l'enregistrement (`RegleNomenclatureService.controler_regle`, lot 3). Fichier illisible = toute règle refusée.
- Un type hors liste rencontré à l'import est signalé (pas bloquant), comme les formats non gérés aujourd'hui.

---

## 4. Nouveau type « Four combiné micro-ondes »

### 4.1 Périmètre (vérifié sur fiches fabricants, voir § 9.2)

> **Liste figée le 2026-11-23 (lot 2)** : `data/corrections/nomenclature_lot2.csv`, **6 104 appareils** (Four −5 517, Micro-ondes −587), relue famille par famille avec le client ; **appliquée en production le 2026-11-23 à 13 h 40** (6 104/6 104 conformes, sauvegarde `data/backups/appareils_20261123_134022_nomenclature_lot2.db`). Elle remplace l'estimation plus bas, gardée pour mémoire (voir « Écarts »).

| Fam. | Règle retenue | Appareils | Source / décision |
|---|---|---|---|
| 1 | Bosch `CMG` (toutes formes) ; `HMG` récent `HMG###@@#(@)` / `HMG####@#(@)` ; + `HMG8601/8621/8701/8721` en Four | 1 471 | [CMG633BS1](https://media3.bosch-home.com/Documents/specsheet/fr-CH/CMG633BS1.pdf) ; les 4 anciennes HMG8 : décision client (leurs 4 homonymes en Micro-ondes et les ~510 autres HMG8xxx restent Micro-ondes) |
| 2 | Siemens `CM`/`HM` + [6-9] + 2 chiffres + `@?@#(@)` ; + 18 `CM485`/`CM585` (Micro-ondes) | 2 309 | [CM585AGS0B « microwave oven with hot air, 60 x 45 »](https://siemens-home.bsh-group.com/uk/en/mkt-product/cooking-and-baking/ovens/compact-ovens/CM585AGS0B) |
| 3 | Neff `C??M` (727 Four + 30 Micro-ondes : `C57M70`, `C1AMG84`/`C1CMG84`) | 757 | [C1AMG84N0B « compact oven with microwave »](https://neff-home.com/uk/productlist/ovens-compact-ovens/ovens/single-microwave-oven/C1AMG84N0B) |
| 4 | AEG `KMK`/`KME`/`KMS`/`KM8` (170) + `KMX` (6) + `CM`/`CME`/`CMK` (34) + `NKM`/`NKO` (17) | 227 | [KMX365060M](https://aeg.co.uk/kitchen/cooking/ovens/compact-oven/kmx365060m), [notice CM7600B « Four à micro-ondes combiné »](https://www.aeg.be/services/eml/asset/da2e91ee-db9a-4041-8751-2dec8086d846/E4RM3Q/250315JEZF/PDF/250315JEZF.pdf), [NKM7N721T](https://www.carrefour.fr/p/four-micro-onde-encastrable-aeg-nkm7n721t-compact-7333394105574) ; `KMF`/`KMR`/`KM4`/`KM7`/`KM9800E` laissés (sans source) |
| 5 | Gaggenau `BM*` | 231 | conforme |
| 6 | Electrolux `EVY` (64 Four + 43 Micro-ondes) + `EVL`/`EVM`/`EVK` forme `EV?#@…` CombiQuick (49 Micro-ondes) | 156 | [EVY7800AOX « four compact deux-en-un »](https://www.gigantti.fi/document/dv_doc_D180001002465827/EVY7800AOX/electrolux-kompaktiuuni-evy7800aox.PDF), [EVLBE08GX](https://www.electrolux.co.uk/kitchen/cooking/ovens/compact-oven/evlbe08gx/) |
| 7 | Ancienne génération BSH : Bosch `HBC8[3-6][KEP]`, Siemens `HB8[3-6][KEP]`, Neff `B67#4` | 953 | [HBC84K553A « compact oven with microwave »](https://www.bosch-home.co.uk/customer-service/HBC84K553A/01), [HBC84E653B](https://bosch-home.co.uk/customer-service/HBC84E653B/01) ; 656 des 953 ont un libellé d'origine qui le dit |

**Écarts avec l'estimation** : gabarit Siemens `CM###@@@#` trop étroit (ratait `CM676G0S1`, 621 appareils) → `CM###@?@#` ; anciennes Siemens `HM` cuisinières = **775** (pas 487), non touchées ; AEG 170 (pas 168 : 2 `KM8100001M` en Four) ; Miele `H … BM` : **aucun** appareil en base ; Whirlpool `AMW 508` et voisins (chaleur pulsée) : **restent Micro-ondes** (Darty « micro-ondes multi-cuissons », vendu comme micro-ondes ; impossible à séparer par la référence).

**Vu au passage, pour le lot 3** : 767 Gaggenau `BS2`/`BSP`/`BS4` en « Four », dont une partie libellée « COMBIVAP » (four vapeur).

Estimation initiale :

| Marque | Règle | Aujourd'hui | Volume |
|---|---|---|---|
| Bosch | `CMG…` ; `HMG` **forme récente** `HMG###@@#` | Four | ~1 300 |
| Siemens | `CM6…CM9`, `HM6…HM9` **forme récente** `CM###@@@#` / `HM###@@@#` | Four | ~2 300 |
| Neff | `C` + 2 car. + **`M`** en 4e position (`C17MS32N0`) | Four (727), Micro-ondes (30) | ~760 |
| AEG | `KMK`, `KME`, `KMS`, `KM8` | Micro-ondes | 168 |
| Gaggenau | `BM…`, `BMP…` | Micro-ondes | 231 |

**Restent Micro-ondes** : Neff `C??W…`, Bosch `BFL`/`BEL`/`BFR`/`BER`, Siemens `BF`/`BE`/`HF`.
**Restent Cuisinière** : 487 anciennes Siemens `HM` de forme ancienne — d'où l'obligation du gabarit.
**À confirmer** : Miele `H … BM`, Electrolux `EVY` (pas de fiche fiable trouvée).

### 4.2 Effets de bord à traiter dans le même lot

- **Site** : le type doit exister côté site **avant** le premier export qui l'utilise (action client — **fait**, confirmé le 2026-11-23).
- **Appellations** (`src/utils/appellations_appareils.py`) : « four micro-ondes » est un synonyme actif de **Micro-ondes** → le désactiver, sinon un micro-ondes simple serait présenté comme le nouveau type. Ajouter l'entrée du nouveau type (genre masculin ; variante proposée « four micro-ondes combiné »). **Piège (lot 2)** : la config enregistrée (`data/export_config.json`, `synonymes_appareils.appareils`) fait foi sur les défauts → **migration ponctuelle** notée dans la config (`migrations`), jouée une seule fois : un réglage refait ensuite par l'utilisateur tient.
- **SEO** (`src/utils/seo_generator.py`) : `_segment_templates_for` prend la clé la plus longue **contenue** dans le type ; « four combiné micro-ondes » tomberait sur le segment **« micro-ondes »** (« Micro-ondes Bosch : … »). Ajouter un segment dédié, et l'entrée `TYPE_NORMALIZATION` correspondante.
- **Titres** (`titre_produit_generator.py`) : vérifier `SEUIL_TYPES_PROCHES` (80 %) et le retrait des types avec le nouveau libellé (plus long). **Vérifié (lot 2)** : aucun code à changer ; le seuil ne joue que sur les fiches mêlant Four et combinés, le libellé long fait retirer une marque avant un type.
- **Autres tests par sous-chaîne** (lot 2) : `lecteur.py` (plus long début = type connu) et `coupe_titre.py` (termes du plus long au plus court) reconnaissent le nouveau libellé ; les filtres de colonne « contient four » le montrent, comme « Four vapeur ».
- **Guide** : section Types + ligne « Nouveautés » sous « En préparation ».

---

## 5. Modèle de données

### 5.1 Table `regles_nomenclature`

```sql
CREATE TABLE regles_nomenclature (
    id            INTEGER PRIMARY KEY,
    portee        TEXT NOT NULL,      -- 'marque' | 'groupe'
    cible         TEXT NOT NULL,      -- nom de marque, ou nom de groupe (groupes_marques)
    cle           TEXT NOT NULL,      -- 'nom' (réf. commerciale) | 'code' (code usine numérique)
    forme         TEXT NOT NULL,      -- 'prefixe' | 'position' | 'gabarit' (déduite du motif)
    motif         TEXT NOT NULL,      -- 'AKZ' | 'EW?F*' | 'HSG###@@#' (syntaxe § 6.1)
    type_resultat TEXT NOT NULL,      -- membre de types_autorises
    statut        TEXT NOT NULL DEFAULT 'proposee',  -- 'proposee' | 'validee' | 'rejetee'
    origine       TEXT NOT NULL,      -- 'decouverte' | 'web' | 'saisie'
    source_url    TEXT,               -- fiche ou notice qui justifie la règle
    note          TEXT,
    couverture    INTEGER,            -- nb d'appareils concernés au dernier calcul
    accord        INTEGER,            -- nb dont le type en base = type_resultat
    calcule_le    TEXT,
    valide_le     TEXT,
    UNIQUE (portee, cible, cle, motif)
);
```

### 5.2 Table `propositions_type`

```sql
CREATE TABLE propositions_type (
    appareil_id  INTEGER PRIMARY KEY REFERENCES appareils(id) ON DELETE CASCADE,
    type_actuel  TEXT,
    type_propose TEXT NOT NULL,
    regle_id     INTEGER REFERENCES regles_nomenclature(id) ON DELETE CASCADE,
    force        TEXT NOT NULL,       -- 'forte' | 'simple' (§ 7)
    signaux      TEXT,                -- JSON : vote pièces, libellé, 2e clé
    cree_le      TEXT NOT NULL
);
```

- Les **refus** réutilisent `refus_completions` (`champ = 'type'`) : un type refusé pour un appareil n'est plus jamais reproposé, comme pour l'auto-complétion.
- Les **corrections acceptées** passent par `EventDrivenSaveService` et laissent une ligne dans `modifications_history` (`action_type` dédié, `old_value` / `new_value`) : retour arrière possible.
- Les **groupes** réutilisent `groupes_marques` de `src/utils/rapprochement_fiche/configuration.py` (pas de seconde liste).
- Schéma existant inchangé : `appareils` n'est pas modifiée.
### 5.3 Acceptations annulables (lot 4)

```sql
CREATE TABLE lots_acceptation_type (
    id INTEGER PRIMARY KEY, regle_id INTEGER, libelle TEXT NOT NULL,
    accepte_le TEXT NOT NULL, nb INTEGER NOT NULL, annule_le TEXT);
CREATE TABLE acceptations_type (
    lot_id INTEGER NOT NULL REFERENCES lots_acceptation_type(id) ON DELETE CASCADE,
    appareil_id INTEGER NOT NULL, type_avant TEXT, type_apres TEXT NOT NULL,
    PRIMARY KEY (lot_id, appareil_id));
```

- L'historique n'a pas d'« annuler » (Cmd+Z ne vaut que pour les lignes affichées) : une acceptation garde donc ses appareils, **un lot par règle**. L'annulation (onglet Acceptations de l'écran) relit le lot et remet le type d'avant par `CorrectionTypesService` (sens `annuler`) : seul un appareil encore au type accepté revient ; un appareil modifié depuis est laissé tel quel.
- Déclencheur : un appareil supprimé quitte ses lots.

- **Codé au lot 3** (`src/data/_db_mixins/nomenclature.py`) tel quel, avec des `CHECK` sur portée, clé, forme, statut, origine et force ; les cascades sont doublées de déclencheurs (elles valent même sans `Config.FOREIGN_KEYS`). Vérifié contre la base réelle (copie par l'API backup, 720 433 appareils) : aucune table de ce nom, aucun conflit. Les refus réutilisent `refus_completions` tel quel : un type refusé n'est plus proposé ni par une règle, ni par l'auto-complétion de l'import (même sens). `propositions_type` est **recalculée en entier** à chaque calcul (une transaction).

---

## 6. Moteur de règles

### 6.1 Normalisation et syntaxe des motifs

- Clé `nom` : réf. commerciale (sinon réf. modèle **sans son suffixe « /01 »**) en majuscules, sans espaces ni ponctuation, si elle contient une lettre — mêmes clés que la liste du lot 2. Clé `code` : réf. modèle (sinon commerciale) entièrement numérique, ≥ 6 chiffres.
- Syntaxe : celle des jokers de filtre de colonne (`src/utils/filtre_colonne.py`, PR #169 **mergée sur main** le 2026-11-23 : on la **réutilise**, pas de second module) — `?` = un caractère, `*` = n'importe quoi ; ajouts propres aux règles : `#` = un chiffre, `@` = une lettre. Motif **ancré au début** (`|` et `!` du filtre non utilisés dans un motif de règle : une règle = un motif).
  - préfixe : `AKZ*` ; position : `EW??F*` (5e car. = F) ; gabarit : `HSG###@@#`.
  - **Ajout du lot 3 : classes `[3-6]`, `[KEP]`** (`HBC8[3-6][KEP]*`, `CM[4-9]##@?@#`), indispensables pour écrire les familles du lot 2. `*` seulement à la fin ; sans `*`, le motif décrit la clé entière. Une exception s'écrit par une règle plus précise (`GKN[12]*` sous `GK*` sous `G*`), jamais par `!`. Code : `filtre_colonne.motif_regle_vers_regex` (les fonctions des filtres de colonne sont inchangées).

### 6.2 Résolution (pour un appareil)

1. Règles **validées** seulement (les proposées servent à la revue, jamais au typage).
2. Portée **marque** avant **groupe** ; la règle de groupe ne s'applique que si la marque n'a aucune règle **décidée** sur ce motif (validée, ou **rejetée** : une règle de marque rejetée retire la marque de la règle de groupe). **Correction du lot 4** : une règle seulement **proposée** ne décide rien (D4) et ne masque plus la règle de groupe. Constat sur la base réelle : la découverte proposait « Whirlpool `AKR3*` → Four » (l'erreur majoritaire) et sa seule présence retirait Whirlpool de la règle validée « groupe Whirlpool `AKR3*` → Plaque » — les 115 propositions fortes disparaissaient.
3. La plus spécifique gagne : gabarit > position > préfixe ; à égalité, motif le plus long.
4. Si les deux clés (`nom`, `code`) donnent un résultat, ils doivent concorder ; sinon → « à vérifier », pas de proposition.

### 6.3 Garde-fous de la découverte automatique

- Préfixe ≥ 3 caractères pour une règle de groupe ; préfixe numérique ≥ 4 chiffres.
- ≥ 20 appareils et ≥ 95 % de pureté pour proposer une règle ; validation croisée (moitié apprend, moitié teste).
- Pas de règle « contient » ; positions et gabarits seulement.
- **Zone grise** : préfixe partagé sans type > 85 % → aucune règle à son niveau ni de position tant qu'une source web (§ 9) n'a pas tranché. **Précision du lot 3** : la descente continue en dessous (sinon « AK » mélangé interdirait « AKP » pur), mais une règle trouvée sous une zone grise le dit dans sa note (« sous la zone grise AK* »), pour la revue.
- Longueurs minimales retenues : préfixe `nom` ≥ 2 caractères pour une marque, ≥ 3 pour un groupe ; clé `code` ≥ 4 chiffres. Entre 85 et 95 % : recherche d'un caractère, au plus 3 positions après le préfixe, qui départage au moins deux types et couvre ≥ 90 % du préfixe.
- **Mesuré au lot 3** sur la base réelle : 7 420 règles candidates, 3 386 zones grises, **3,3 s** (test de charge synthétique 720 000 appareils : ~3 s, garde-fou < 30 s).
- **Lot 4** : la découverte ne repropose pas un motif déjà **tranché** (règle validée ou rejetée, de la marque ou de son groupe) : 17 candidates écartées sur la base réelle, dont `AKR3*` → Four. Les nouvelles règles sont enregistrées en `proposee` ; la note « sous la zone grise X* » est gardée en tête quand on édite la note. Une règle de groupe **doublée** par la même règle de marque (≈ 1 500 cas) ne couvre que les autres marques du groupe : la fiche le dit.
- **Mesures après une découverte** : avec ≈ 7 400 règles, le test règle par règle des mesures faisait passer le calcul des propositions de 3 s à **126 s** ; les préfixes purs sont désormais cherchés par les débuts de la clé (`_ReglesIndexees`) : **5 à 7 s**, mesures et propositions identiques (vérifié sur 7 464 règles).

---

## 7. Force d'une proposition

| Force | Condition | Usage |
|---|---|---|
| **forte** | règle validée **et** (2e clé d'accord **ou** vote des pièces > 60 % **ou** libellé d'origine d'accord), types **éloignés** | proposée en tête de revue, acceptation groupée possible |
| **simple** | règle validée seule, ou types **voisins** (les pièces ne départagent pas réfrigérateur/congélateur, four/cuisinière…) | revue ligne à ligne |

Le vote des pièces = type des **autres** appareils partageant ses pièces (`piece_associations`), l'appareil lui-même exclu.
Le libellé d'origine (`other_ref`) n'est **jamais** un signal seul (cas « Four Vapeur » Whirlpool).

---

## 8. Parcours utilisateur

### 8.1 Écran « Règles de nomenclature » (menu Données, D14)

- Liste filtrable : marque/groupe, motif, type, statut, couverture, accord, source.
- Fiche d'une règle : exemples d'appareils concernés (dont ceux en désaccord), lien source, bouton **Valider / Rejeter**, champ note.
- Bouton « Chercher de nouvelles règles » : lance la découverte (§ 6.3) en arrière-plan (comme les comptages du gestionnaire de pièces, PR #166), résultat en statut `proposee`.
- Dialogues en `show()` + callbacks (pas d'`exec_()`), styles via StyleManager, icônes qtawesome.
- **Codé au lot 4** (`src/ui/regles_nomenclature_dialog.py`) : filtre de motif = syntaxe des filtres de colonne (`filtre_colonne.correspond_au_filtre`, même sens que le SQL) ; cases « changeraient des appareils » et « pureté ≥ 98 % (D7) » ; colonnes couverture, accord, désaccords, proposés, source (lien), zone grise (⚠ + bandeau sur la fiche) ; exemples lus pour les seules marques visées (0,1 à 0,3 s) ; Valider / Rejeter / Remettre en proposée, sur plusieurs règles avec récapitulatif (D16). Calculs en arrière-plan (`src/ui/calcul_nomenclature.py`) : QThread sur une connexion **en lecture seule** qui réutilise les lectures du mixin ; l'écriture se fait ensuite sur le fil principal et **écarte les propositions périmées** (type changé ou refus posé pendant le calcul). Mesuré : découverte 3,3 à 5 s, plus long blocage de l'interface 0,16 s ; une découverte enchaîne un recalcul (les mesures de la découverte ne tiennent pas compte du masquage § 6.2).

### 8.2 Revue des propositions

- Réutiliser le circuit « à vérifier » existant (navigation ▲▼ `TableController._CRITERES_NAV`, PR #150) avec un critère « type proposé ».
- Accepter / refuser une ligne, ou **toutes les lignes fortes d'une règle** (D8) : récapitulatif avant application (nombre, comptage par type avant/après), une entrée d'historique annulable.
- **Codé au lot 4** :
  - fenêtre « Types proposés » (`src/ui/propositions_type_dialog.py`, gabarit `FenetreRevue` des suggestions) : regroupée par règle (celles qui ont des fortes d'abord), puces Fortes / Simples / Validation groupée, détail des signaux ; une validation sur plusieurs lignes ne retient que les **groupables** (D8 + D13), un bandeau dit combien restent en attente ; « Appliquer » (et la fermeture) passent par le récapitulatif ;
  - tableau : critère `type_propose` de `TableController._CRITERES_NAV` (flèches ▲▼ autour du bouton « Types proposés (N) », ⇧⌥⌘ Page préc./suiv.), cellule Type teintée vert d'eau et bulle, clic droit « Accepter / Refuser le type proposé » (plusieurs lignes : les seules groupables, après récapitulatif) ;
  - écriture : `RevuePropositionsService` → `CorrectionTypesService` → `EventDrivenSaveService.enregistrer_champs_appareils` ; historique au format d'une modification de Type, provenance « règles de nomenclature, Gaggenau BS* → Four vapeur » (la même pour tout un lot) ; refus dans `refus_completions` (champ `type`), jamais reproposés ; la page affichée est relue.
  - mesuré sur copie de la base réelle : revue de 983 propositions ouverte en 0,1 s ; récapitulatif Gaggenau (767 : Four 95 417 → 94 650, Four vapeur 3 443 → 4 210) 0,07 s ; acceptation des 767 puis annulation 0,07 s chacune, comptage conforme.

### 8.3 Import

- Appareil importé sans type, ou avec un type hors liste : la règle validée propose le type, l'appareil reste « à vérifier » (comme une auto-complétion tracée).
- Le libellé du fichier ne l'emporte pas sur une règle validée contraire : conflit → « à vérifier ».

---

## 9. Catalogue initial (règles à faire valider)

### 9.1 Corrections sûres (lot 1)

Liste **figée le 2026-11-23**, relue famille par famille avec le client : **2 512 appareils**, versionnée dans `data/corrections/nomenclature_lot1.csv` (PR du lot 1, branche `claude/nomenclature-lot1`).

| Fam. | Appareils | Type actuel → nouveau | Lignes | Justification |
|---|---|---|---|---|
| 1 | `AKP*`, `AKZ*` (dont `AKZM`, `AKPM`) sauf `AKZ#S*`, Whirlpool + Ignis | Four vapeur → **Four** | 1 891 | fours multifonction pyrolyse/catalyse ([Darty AKZ 430](https://www.darty.com/nav/achat/encastrable/four_classique/four_encastrable/whirlpool_akz_430_ix_inox.html), [Auchan AKZ513](https://www.auchan.fr/whirlpool-four-akz513ix-65-l-multifonction-chaleur-pulsee-nettoyage-pyrolyse-a/pr-C1470077), [Que Choisir AKZM8480IX](https://www.quechoisir.org/comparatif-four-encastrable-n407/whirlpool-akzm8480ix-p188528/)) ; le `S` final (`AKZ9 6230 S`) = coloris |
| 2 | Whirlpool `AKZ#S*` | Four → **Four vapeur** | 5 | [BUT AKZ9S8270NB](https://www.but.fr/produits/8003437836220/Four-encastrable-vapeur-WHIRLPOOL-AKZ9S8270NB-73L.html) |
| 3 | Bosch `HSG` + 3-4 chiffres + 1-2 lettres + chiffre (+ lettre de marché) | Four → **Four vapeur** | **550** (v0.1 : 457) | [fiche HSG636BB1](https://media3.bosch-home.com/Documents/specsheet/fr-BE/HSG636BB1.pdf), [HSG7361B1 rangé « fours vapeur » par Bosch](https://www.bosch-home.com/ch/fr/product/cuisine-et-cuisson/appareils-de-cuisson-a-la-vapeur/fours-vapeur/HSG7361B1), [HSG656XB6A](https://www.bosch-home.com.au/en/mkt-product/HSG656XB6A) ; anciennes `HSG` + 6 chiffres (cuisinières) non touchées |
| 4 | Haier `XS…`/`XF…` (4), Hoover `HI 4A4S…` (1), Whirlpool `ADG670/UD`, `ADG814/UD`, `ADG826` (3, codes `851…`) | Lave-linge → **Lave-vaisselle** | 8 | pièces 80-88 %, [Haier XS 4A4M4BB](https://www.haier-europe.com/fr_CH/lave-vaisselle/32901923/xs-4a4m4bb/) |
| 5 | Bosch `KAN56V40SA` | Lave-linge → **Réfrigérateur** | 2 | libellé « Combiné SBS », pièces 99 % |
| 6 | Balay `3SB093BC`, `3SB093XC` | Réfrigérateur → **Sèche-linge** | 3 | libellé ; 77 autres `3SB` en sèche-linge |
| 7 | Miele `TE 717I WP`, `TS 300B WP` | Lave-linge → **Sèche-linge** | 2 | libellé + pièces |
| 8 | Electrolux `EW6HI69CO`, `EW6HI81CB` | Lave-linge → **Sèche-linge** | 2 | `EW?H` = sèche-linge ([Auchan EW6HI4936AB](https://www.auchan.fr/electrolux-seche-linge-pompe-a-chaleur-ew6hi4936ab/pr-9f25e7f6-ddbd-4f71-bad6-1b4d025a1bbb)) |
| 9 | Whirlpool `6AKR958IX` | Four → **Hotte** | 1 | libellé « Hotte », pièces 100 % (**pas** de règle `AKR` = hotte, voir § 9.3) |
| 10 | Whirlpool `AMW` en « Four » (582, 583, 589-599, 882) | Four → **Four vapeur** | 44 | décision client : AMW 583 = four vapeur ([catalogue Whirlpool 2012](https://www.yumpu.com/fr/document/view/16747760/appareils-encastrables-2012-whirlpool), [Dampfgarer](https://www.alternate.at/Whirlpool/AMW-583-IX-Dampfgarer/html/product/1417241)) ; confirmés aussi [582](https://www.whirlpool.com.hk/chinese/../media/wysiwyg/Downloads/Factsheet/AMW582-IX.pdf), [591](https://www.electromenager-compare.com/four-WHIAMW591IXL-WHIRLPOOL-AMW-591IXL.htm), [592](https://www.electromenager-compare.com/four-WHIAMW592IXL-WHIRLPOOL-AMW-592IXL.htm), [597](https://www.manualslib.com/manual/3132273/Whirlpool-Amw-597.html) ; 589, 590, 596, 598, 599, 882 sans source, inclus par décision client |
| 10 | Whirlpool `MT263WH` | Four → **Micro-ondes** | 2 | pièces 95 % |
| 11 | Siemens `HL54425NN/01`, `HL54425SC/01` | Four → **Cuisinière** | 2 | libellé « Cuisinières électriques » ; 8 autres `HL54425` déjà en cuisinière |

Comptage attendu (base du 2026-11-23) : Four +1 287, Four vapeur −1 292, Lave-linge −14, Lave-vaisselle +8, Sèche-linge +7, Cuisinière +2, Micro-ondes +2, Hotte +1, Réfrigérateur −1.

Exécution : `scripts/corriger_types_nomenclature.py` — simulation par défaut ; un appareil dont le type a changé depuis la liste est ignoré, jamais écrasé ; sauvegarde avant écriture ; une ligne d'historique par appareil (« [Type] 'a' → 'b' », provenance « règles de nomenclature, lot1 ») ; `--annuler` pour le retour arrière.

### 9.2 Catalogue des règles validées (lot 3)

Catalogue **versionné** `data/regles_nomenclature.csv` : **61 règles**, toutes `validee`, relues famille par famille avec le client le 2026-11-23 (D7, D12). Chargé par `scripts/regles_nomenclature.py catalogue --ecrire` (une règle déjà en base n'est jamais écrasée).

**Mesure sur la base réelle** (copie du 2026-11-23, 720 433 appareils) : 20 708 appareils couverts, **983 propositions**, 0 conflit entre clés, **0 proposition sur les 8 616 appareils des lots 1 et 2** (critère du lot 3, test automatique sur les deux listes figées) ; les règles du combiné retrouvent la liste du lot 2 à l'appareil près (sauf les 4 `HMG8601…`, sans règle). Calcul complet : 3,5 s.

Colonnes : pureté (part déjà au type), vote des pièces, 2e clé (code usine), propositions produites.

| Portée | Motif(s) | Type | n | Pureté | Signaux | Prop. | Classement / source |
|---|---|---|---|---|---|---|---|
| Electrolux | `EW?H*` | Sèche-linge | 658 | 100 % | pièces 100 %, 2e clé 100 % | 0 | D7 d'office ; [EW9H3803D](https://www.electromenager-compare.com/seche-linge-ELEEW9H3803D-ELECTROLUX-EW9H3803D.htm) |
| Electrolux | `EW?F*`, `EW?T*` | Lave-linge | 2 974 | 100 % | pièces 100 %, 2e clé 100 % | 0 | D7 d'office |
| Electrolux | `EW?D*` | Sèche-linge | 458 | 99,6 % | — | 2 | client (lot 3) ; `EW9D…VCP` introuvables |
| Neff | `C??W*` | Micro-ondes | 65 | 100 % | pièces 32/32 | 0 | D7 d'office |
| Hotpoint-Ariston | `AQC*` | Sèche-linge | 86 | 100 % | pièces 100 %, 2e clé 100 % | 0 | D7 d'office |
| Hotpoint-Ariston | `AQD*`, `AQM*` | Lavante-séchante | 164 | 100 % | libellé 164/164 | 0 | une par une, validée |
| Candy | `GO#W*`, `CO#W*`, `GVW*`, `GVSW*`, `CSW*`, `GOW*` | Lavante-séchante | 265 | 98,9 % | pièces 0 (voisins) | 3 | une par une, validée ; [GO4W264](https://www.electromenager-compare.com/lave-linge-CANGO4W264-CANDY-GO4W264.htm) |
| Bosch | `HBC??D*` | Four vapeur | 135 | 95,6 % | libellé 125/129 | 6 | une par une, validée (D = Dampf) |
| Siemens | `CI??W*` | Cave à vin | 53 | 100 % | 8 votes | 0 | une par une, validée |
| De Dietrich | `DOV*` | Four vapeur | 52 | 100 % | libellé 51/52 | 0 | une par une, validée |
| Bosch, Siemens, Neff, AEG, Gaggenau, Electrolux | 24 motifs du lot 2 (§ 4.1), Siemens `CM[4-9]##@?@#(@)` / `HM[6-9]##@?@#(@)` | Four combiné micro-ondes | 6 100 | 100 % | pièces 0 (type neuf) : la source web tient lieu de 2e signal | 0 | lot 2 (D10) |
| AEG | `KMF*` | Four combiné micro-ondes | 4 | 0 % | — | 4 | [notice KME/KMF761080M « microwave combi-oven »](https://manuals.online/aeg/microwave-oven/kmf761080m/user-manual/wyhx) |
| Gaggenau | `BS*` | Four vapeur | 1 148 | 33 % | libellés « Combivap » | **767** | [combi-vapeur série 200](https://www.gaggenau.com/gb/products-list/ovens/200-series/combi-steam-ovens), [BSP220100](https://media3.gaggenau.com/Documents/specsheet/en-ZZ/BSP220100.pdf), [BSP 270/271](https://www.architonic.com/en/product/gaggenau-combi-steam-oven-200-series-bsp-270-bsp-271/20291944) ; BS270 sans fiche exacte |
| Liebherr | `G*` / `GK*` / `GKN[12]*` / `GDC*` | Congélateur / Réfrigérateur / Congélateur / Réfrigérateur | 2 444 | — | GK : pièces 98 %, 2e clé 291/291 | 26 (`GNes` side-by-side → Congélateur) | une par une, validée |
| Whirlpool, Ignis | `AKP*`, `AKZ*` / `AKZ#S*` | Four / Four vapeur | 5 178 | 99,9 % | — | 0 | lot 1, familles 1-2 |
| groupe Whirlpool | `AKR[4-9]*` / `AKR3*` | Hotte / Plaque | 730 | — | libellés « Plaque Email Gaz » | 115 (Four → Plaque) | [AKR 317](https://www.electromenager-compare.com/table-de-cuisson-WHIAKR317IX-WHIRLPOOL-AKR-317IX.htm), [AKR 312](https://www.electromenager-compare.com/table-de-cuisson-WHIAKR312IX-WHIRLPOOL-AKR-312IX.htm) ; `AKR0`/`AKR2` sans règle |
| groupe Whirlpool | `AGB*` | Lave-vaisselle | 94 | 91,5 % | code usine `851…` | 8 (Cuisinière →) | client (lot 3) |
| Beko | `FSE[56]*`, `CSE[56]*` / `CSE3*` / `FSE2*` | Cuisinière / Réfrigérateur / Congélateur | 100 | 48 % | — | 52 (Four → Cuisinière) | [fiche Beko FSE68300GACS](https://www.beko.fr/sites/default/files/Art_FicheProduit_FSE68300GACS.pdf), [Auchan FSE67300](https://www.auchan.fr/beko-cuisiniere-vitroceramique-fse67300xcs-60-cm-4-foyers-four-multifonction/pr-C1602081) |

Propositions par force : **115 fortes** (`AKR3*`, libellé d'accord, types éloignés), 868 simples. Aucune n'est appliquée au lot 3 : elles attendent la revue (lot 4).

Retiré du catalogue initial : Bauknecht `EMV`/`EMZ`/`EMC` (zone grise, § 9.3) ; Bosch `HMG8601/8621/8701/8721` (décision ponctuelle du lot 2 : une règle reproposerait les 4 homonymes laissés en Micro-ondes).

### 9.3 Doutes ouverts (pas de règle avant source)

- ~~Whirlpool `AGB`~~ : **tranché au lot 3** — `AGB*` → Lave-vaisselle (les 8 « Cuisinière » portent un code usine `851…` de lave-vaisselle).
- ~~Electrolux `EW9D…`~~ : **tranché au lot 3** — `EW?D*` → Sèche-linge (456/458) ; les 2 `EW9D…VCP` restent introuvables en ligne.
- **Bauknecht `EM*`** (662 appareils) : **zone grise** (lot 3). Les sites de pièces rangent `EMC 7253`, `EMV 7263`, `EMZD 5265` en « Herd/Backofen » ([ersatzteilshop EMV 7263](https://www.ersatzteilshop.de/ersatzteile-fuer/bauknecht/emv-7263-in-855643122000.html), [ersatzteile-24 EMC 7253](https://www.ersatzteile-24.com/BAUKNECHT/BAUKNECHT_EMC7253IN2_855646322500/855646322502.html)) : les « Four vapeur » ressemblent à la pollution Whirlpool AKP (§ 2.4) ; `EMCC`/`EMCH` sont de vrais micro-ondes. Aucune règle avant une fiche fabricant.
- AEG `KMR` (`KMR721000B`, rangé « four à micro-ondes » sans détail : [manuall](https://manuall.fr/aeg-kmr721000b-micro-onde/)), `KM4`, `KM7`, `KM9800E` : sans source, laissés tels quels (lot 3).
- Whirlpool `AKR0`/`AKR2` : mélangés (hottes, plaques, « fours »), sans règle (lot 3).
- Hoover `HWC…` : 10 « Réfrigérateur » qui ressemblent à des caves à vin (vu au lot 3, non vérifié).
- Hoover : le `W` signifie lave-linge (`HW`, `H3W`) — **ne pas** étendre la règle Candy au groupe.
- ~~Beko `CSE…`/`FSE…`~~ : **tranché au lot 3** par position (`[56]` = cuisinière, `CSE3` réfrigérateur, `FSE2` congélateur) ; [CSE 67301 GW](https://www.electromenager-compare.com/cuisiniere-BEKCSE67301GW-BEKO-CSE-67301-GW.htm).
- ~~Miele `H … BM`, Electrolux `EVY`~~ : **tranché au lot 2** — Miele : aucun appareil en base ; `EVY` → Four combiné micro-ondes (§ 4.1, fam. 6).
- Whirlpool `AMW 508` et voisins à chaleur pulsée (« micro-ondes combiné » chez Darty) : **restent Micro-ondes** (décision lot 2) ; AEG `KMF`/`KMR`/`KM4`/`KM7`/`KM9800E` : sans source, laissés tels quels.
- ~~Whirlpool `AKR`~~ : **tranché au lot 3** par numéro — `AKR[4-9]*` Hotte (615 à 100 %), `AKR3*` Plaque (tables gaz) ; `AKR0`/`AKR2` restent ouverts (ci-dessus).
- Whirlpool `AMW` : série imbriquée — `AMW 5xx` jusqu'à 578 et 584-588 = micro-ondes, 582-583 et 589-599 = fours vapeur compacts. Une règle devra lister les numéros, pas un préfixe.

---

## 10. Découpage en lots (une PR par lot, branche dédiée)

| Lot | Contenu | Visible ? |
|---|---|---|
| 1 | Corrections sûres § 9.1 via `EventDrivenSaveService`, historique, liste relue avant exécution | données |
| 2 | Type « Four combiné micro-ondes » : appellations (+ migration de la config), segment SEO, normalisation, reclassement § 4.1 (6 104) — `types_autorises` reporté au lot 3 (D10) | oui (+ Guide) |
| 3 | Liste fermée `types_autorises` (§ 3), tables § 5, moteur § 6 sans écran, catalogue § 9.2, tests — **codé** (`RegleNomenclatureService`, `src/utils/nomenclature/`, `scripts/regles_nomenclature.py`) | non |
| 4 | Écran Règles § 8.1 + revue § 8.2 — **codé** (`ReglesNomenclatureDialog`, `PropositionsTypeDialog`, `RevuePropositionsService`, `CalculNomenclature`, tables § 5.3) | oui (+ Guide) |
| 5 | Typage à l'import § 8.3 | oui (+ Guide) |
| à part | Ménage marques : retirer « SMEG » collé dans 1 331 réf. ; vérifier Concord/Concorde | données |

Le lot 2 dépend de la création du type sur le site (action client).

---

## 11. Critères d'acceptation et zéro régression

- Avant/après chaque lot : nombre d'appareils par type, comparé ; tout écart non prévu = arrêt.
- Lot 2 : les exports d'un échantillon de fiches hors du nouveau type sont **identiques** octet pour octet (métas, titres, CSV). **Mesure retenue** : toutes les pièces (6 442), en deux contrôles — nouveau code sur ancienne base (seules les métas des Micro-ondes citant « four micro-ondes » peuvent changer), puis nouveau code sur base reclassée (seules les fiches liées à un appareil reclassé, en propre ou par équivalente, peuvent changer).
- Tests unitaires du moteur sur les cas pièges : `HM633GBS1` (combiné) vs ancienne `HM…` (cuisinière) ; `AKZ9S8270NB` (vapeur) vs `AKZ513IX` (four) ; `AWE8230ZEN` (lave-linge malgré le Z) ; `GO4W264` (Candy, lavante) vs `H3W 69TME` (Hoover, lave-linge).
- Test de charge : découverte complète < 30 s sur 720 000 appareils (mesuré 15 s en script ; **lot 3 : 3,3 s** sur la base réelle, ~3 s en test synthétique).
- Lot 3 : appliqué aux listes figées des lots 1 et 2, le catalogue ne propose **aucun** autre type que celui déjà posé (test automatique) ; aucune sortie d'export ne change (banc d'exports du lot 2, ancien code contre nouveau, même base).
- Rejouer les tests avec le style global (piège eventFilter) et `compileall`.
- Lot 4 : fenêtres ouvertes avec le style global (écran, revue, vraie fenêtre principale), revue ligne à ligne et groupée, récapitulatif, annulation (appareil modifié depuis laissé tel quel), refus jamais reproposé après recalcul, règle proposée sans effet sur une règle validée ; banc d'exports A/B (code de `main` contre code du lot 4, même copie de la base) identique.

---

## 12. Questions ouvertes — tranchées le 2026-11-23

1. Nom exact du nouveau type → **« Four combiné micro-ondes »** (D6).
2. Règles § 9.2 issues de la seule découverte → **d'office si ≥ 98 % + 2e signal, sinon une par une** (D7). Conséquence sur le catalogue § 9.2 : Liebherr `GK*` (96,9 %) et Bauknecht `EMV/EMZ/EMC` (96 %) passent **une par une** ; les autres (100 %, 99 %, 98 %) sont validées d'office si le vote des pièces concorde au calcul du lot 3.
3. Acceptation groupée des fortes → **oui, avec récapitulatif** (D8) ; à intégrer au § 8.2.
4. Lignes accessoires (recompte : 100 lignes + 117 « Kit de recyclage ») → **exclues des règles, chantier à part** (D9) ; la découverte (§ 6.3) les ignore comme appareils sources et comme types résultats.
