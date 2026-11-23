# Cahier des charges — Règles de nomenclature des appareils (types justes)

**Statut :** Proposé — à valider, rien n'est codé
**Version :** 0.1 (2026-11-23)
**Contexte :** Le client veut que ses clients retrouvent leur appareil par une recherche, sous la bonne marque et le bon type. Les fabricants codent le type dans leurs références (BSH : `S…` = lave-vaisselle ; Electrolux : PNC `911…` = lave-vaisselle ; Neff : `C17M…` = four combiné micro-ondes). Ce document définit comment l'outil apprend, fait valider et applique ces **règles de nomenclature** pour corriger et compléter le type des appareils.

---

## 0. Décisions client (2026-11-23)

| # | Décision |
|---|---|
| D1 | **Pas d'attributs.** La base du site n'en a pas : chaque appareil a **un seul type**, choisi dans une liste fermée. |
| D2 | Les combinés restent des **types à part entière** (« Four vapeur » reste un type). |
| D3 | Création d'un **nouveau type « Four combiné micro-ondes »** (nom à confirmer, voir § 12), sur le modèle de « Four vapeur ». |
| D4 | Toute correction passe par une **validation humaine** (une règle validée = des centaines d'appareils) ; aucune correction silencieuse. |
| D5 | En cas de doute, on cherche des réponses **hors de l'application** (fiches fabricants, notices) et on garde la source. |

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

- Nouvelle liste **`types_autorises`** (config JSON versionnée, comme `data/export_config.json`), initialisée avec les types présents en base au moment du lot 3, **plus « Four combiné micro-ondes »**.
- Une règle ne peut produire qu'un type de cette liste (contrôle à l'enregistrement de la règle).
- Un type hors liste rencontré à l'import est signalé (pas bloquant), comme les formats non gérés aujourd'hui.

---

## 4. Nouveau type « Four combiné micro-ondes »

### 4.1 Périmètre (vérifié sur fiches fabricants, voir § 9.2)

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

- **Site** : le type doit exister côté site **avant** le premier export qui l'utilise (action client).
- **Appellations** (`src/utils/appellations_appareils.py`) : « four micro-ondes » est un synonyme actif de **Micro-ondes** → le désactiver, sinon un micro-ondes simple serait présenté comme le nouveau type. Ajouter l'entrée du nouveau type (genre masculin ; variante proposée « four micro-ondes combiné »).
- **SEO** (`src/utils/seo_generator.py`) : `_segment_templates_for` prend la clé la plus longue **contenue** dans le type ; « four combiné micro-ondes » tomberait sur le segment **« micro-ondes »** (« Micro-ondes Bosch : … »). Ajouter un segment dédié, et l'entrée `TYPE_NORMALIZATION` correspondante.
- **Titres** (`titre_produit_generator.py`) : vérifier `SEUIL_TYPES_PROCHES` (80 %) et le retrait des types avec le nouveau libellé (plus long).
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
    forme         TEXT NOT NULL,      -- 'prefixe' | 'position' | 'gabarit'
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

---

## 6. Moteur de règles

### 6.1 Normalisation et syntaxe des motifs

- Clé `nom` : réf. commerciale (sinon réf. modèle) en majuscules, sans espaces ni ponctuation, si elle contient une lettre. Clé `code` : réf. modèle (sinon commerciale) entièrement numérique, ≥ 6 chiffres.
- Syntaxe : celle des jokers de filtre de colonne (`src/utils/filtre_colonne.py`, PR #169 — **pas encore mergée** : à réutiliser si elle l'est au lot 3, sinon module propre) — `?` = un caractère, `*` = n'importe quoi ; ajouts : `#` = un chiffre, `@` = une lettre. Motif **ancré au début**.
  - préfixe : `AKZ*` ; position : `EW??F*` (5e car. = F) ; gabarit : `HSG###@@#`.

### 6.2 Résolution (pour un appareil)

1. Règles **validées** seulement (les proposées servent à la revue, jamais au typage).
2. Portée **marque** avant **groupe** ; la règle de groupe ne s'applique que si la marque n'a aucune règle sur ce motif.
3. La plus spécifique gagne : gabarit > position > préfixe ; à égalité, motif le plus long.
4. Si les deux clés (`nom`, `code`) donnent un résultat, ils doivent concorder ; sinon → « à vérifier », pas de proposition.

### 6.3 Garde-fous de la découverte automatique

- Préfixe ≥ 3 caractères pour une règle de groupe ; préfixe numérique ≥ 4 chiffres.
- ≥ 20 appareils et ≥ 95 % de pureté pour proposer une règle ; validation croisée (moitié apprend, moitié teste).
- Pas de règle « contient » ; positions et gabarits seulement.
- **Zone grise** : préfixe partagé sans type > 85 % → aucune règle proposée tant qu'une source web (§ 9) n'a pas tranché.

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

### 8.1 Écran « Règles de nomenclature » (menu Gestion)

- Liste filtrable : marque/groupe, motif, type, statut, couverture, accord, source.
- Fiche d'une règle : exemples d'appareils concernés (dont ceux en désaccord), lien source, bouton **Valider / Rejeter**, champ note.
- Bouton « Chercher de nouvelles règles » : lance la découverte (§ 6.3) en arrière-plan (comme les comptages du gestionnaire de pièces, PR #166), résultat en statut `proposee`.
- Dialogues en `show()` + callbacks (pas d'`exec_()`), styles via StyleManager, icônes qtawesome.

### 8.2 Revue des propositions

- Réutiliser le circuit « à vérifier » existant (navigation ▲▼ `TableController._CRITERES_NAV`, PR #150) avec un critère « type proposé ».
- Accepter / refuser une ligne, ou **toutes les lignes d'une règle** (forte seulement).

### 8.3 Import

- Appareil importé sans type, ou avec un type hors liste : la règle validée propose le type, l'appareil reste « à vérifier » (comme une auto-complétion tracée).
- Le libellé du fichier ne l'emporte pas sur une règle validée contraire : conflit → « à vérifier ».

---

## 9. Catalogue initial (règles à faire valider)

### 9.1 Corrections sûres (lot 1)

| Appareils | Type actuel → nouveau | Justification |
|---|---|---|
| `AKP*`, `AKZ*` sauf `AKZ#S*`, groupe Whirlpool (1 891) | Four vapeur → **Four** | fours multifonction pyrolyse/catalyse ([Darty AKZ 430](https://www.darty.com/nav/achat/encastrable/four_classique/four_encastrable/whirlpool_akz_430_ix_inox.html), [Auchan AKZ513](https://www.auchan.fr/whirlpool-four-akz513ix-65-l-multifonction-chaleur-pulsee-nettoyage-pyrolyse-a/pr-C1470077)) |
| Whirlpool `AKZ#S*` | Four → **Four vapeur** | [BUT AKZ9S8270NB](https://www.but.fr/produits/8003437836220/Four-encastrable-vapeur-WHIRLPOOL-AKZ9S8270NB-73L.html) |
| Bosch `HSG###@@#` (457) | Four → **Four vapeur** | [fiche HSG636BB1](https://media3.bosch-home.com/Documents/specsheet/fr-BE/HSG636BB1.pdf), [HSG836NC1](https://media3.bosch-home.com/Documents/specsheet/fr-BE/HSG836NC1.pdf) |
| Haier `XS…`, `XF…` ; Hoover `HI 4A4S…` ; Whirlpool `ADG670/UD`, `ADG814/UD`, `ADG826` | Lave-linge → **Lave-vaisselle** | pièces 85-94 % lave-vaisselle + nomenclature |
| Bosch `KAN56V40SA` | Lave-linge → **Réfrigérateur** | libellé « Combiné SBS », pièces 99 % |
| Balay `3SB093BC`, `3SB093XC` | Réfrigérateur → **Sèche-linge** | libellé + pièces |
| Miele `TE 717I WP`, `TS 300B WP` | Lave-linge → **Sèche-linge** | libellé + pièces |
| Electrolux `EW6HI69CO`, `EW6HI81CB` | Lave-linge → **Sèche-linge** | `EW?H` = sèche-linge ([Auchan EW6HI4936AB](https://www.auchan.fr/electrolux-seche-linge-pompe-a-chaleur-ew6hi4936ab/pr-9f25e7f6-ddbd-4f71-bad6-1b4d025a1bbb)) |
| Whirlpool `6AKR958IX` | Four → **Hotte** | `AKR` = hottes, libellé « Hotte » |
| Whirlpool `AMW583IX`, `MT263WH` | Four → **Micro-ondes** | pièces 80-100 % |
| Siemens `HL54425NN`, `HL54425SC` | Four → **Cuisinière** | libellé « Cuisinières électriques » |

La liste exacte (identifiants) est figée au début du lot 1 par une requête relue avec le client.

### 9.2 Règles par position confirmées (lot 3, statut `validee` d'emblée si le client l'accepte)

| Portée | Motif | Type | Source |
|---|---|---|---|
| Electrolux | `EW?H*` | Sèche-linge | [Electrolux EW9H3803D](https://www.electromenager-compare.com/seche-linge-ELEEW9H3803D-ELECTROLUX-EW9H3803D.htm) |
| Electrolux | `EW?F*`, `EW?T*` | Lave-linge | découverte, 100 % |
| Candy | `GO#W*`, `CO#W*`, `GVW*`, `GVSW*`, `CSW*`, `GOW*` | Lavante-séchante | [Candy GO4W264](https://www.electromenager-compare.com/lave-linge-CANGO4W264-CANDY-GO4W264.htm), [Que Choisir GVW](https://www.quechoisir.org/comparatif-lave-linge-sechant-n293/candy-gvw5107lwhc-s-p182355/) |
| Bosch | `HBC??D*` | Four vapeur | découverte 99 % (D = Dampf) |
| Bosch | `HMG###@@#`, `CMG*` | Four combiné micro-ondes | [fiche HMG8764C1](https://media3.bosch-home.com/Documents/specsheet/fr-BE/HMG8764C1.pdf), [CMG633BS1](https://media3.bosch-home.com/Documents/specsheet/fr-CH/CMG633BS1.pdf) |
| Siemens | `CI??W*` | Cave à vin | découverte 100 % |
| Siemens | `CM###@@@#`, `HM###@@@#` | Four combiné micro-ondes | [fiche CM633GBS1](https://media3.bsh-group.com/Documents/specsheet/fr-BE/CM633GBS1.pdf) |
| Neff | `C??M*` | Four combiné micro-ondes | [fiche C17MS32N0](https://media3.neff-international.com/Documents/specsheet/fr-FR/C17MS32N0.pdf) |
| Neff | `C??W*` | Micro-ondes | découverte |
| AEG | `KMK*`, `KME*`, `KMS*`, `KM8*` | Four combiné micro-ondes | [AEG KMK968000T](https://www.aeg.co.uk/kitchen/cooking/ovens/compact-oven/kmk968000t) |
| Gaggenau | `BM*` | Four combiné micro-ondes | [fiche BMP251130](https://media3.gaggenau.com/Documents/specsheet/fr-FR/BMP251130.pdf) |
| Gaggenau | `BS4*` | Four vapeur | découverte 98 % (série 400 combi-vapeur) |
| Liebherr | `GK*` | Réfrigérateur | découverte (339/350) |
| Liebherr | `G*` hors `GK*` | Congélateur | découverte |
| Bauknecht | `EMV*` / `EMZ*` / `EMC*` | Four vapeur / Four / Micro-ondes | découverte 96 % |
| De Dietrich | `DOV*` | Four vapeur | découverte 100 % |
| Hotpoint-Ariston | `AQD*`, `AQM*` / `AQC*` | Lavante-séchante / Sèche-linge | découverte 100 % |

### 9.3 Doutes ouverts (pas de règle avant source)

- Whirlpool `AGB` : mélange lave-vaisselle (`AGB 669/671`, [notice](https://www.notice-facile.com/en/manual/38282/whirlpool+agb-669-wp-_f)) et cuisinières → trancher par le code usine (`851…` = lave-vaisselle).
- Electrolux `EW9D…` : introuvable en ligne.
- Hoover : le `W` signifie lave-linge (`HW`, `H3W`) — **ne pas** étendre la règle Candy au groupe.
- Beko `CSE…`/`FSE…` : cuisinières ([CSE 67301 GW](https://www.electromenager-compare.com/cuisiniere-BEKCSE67301GW-BEKO-CSE-67301-GW.htm)) — la règle « Four » de Beko est trop large.
- Miele `H … BM`, Electrolux `EVY` : combinés micro-ondes probables, non confirmés.

---

## 10. Découpage en lots (une PR par lot, branche dédiée)

| Lot | Contenu | Visible ? |
|---|---|---|
| 1 | Corrections sûres § 9.1 via `EventDrivenSaveService`, historique, liste relue avant exécution | données |
| 2 | Type « Four combiné micro-ondes » : liste `types_autorises`, appellations, segment SEO, normalisation, reclassement § 4.1 | oui (+ Guide) |
| 3 | Tables § 5, moteur § 6 sans écran, catalogue § 9.2, tests | non |
| 4 | Écran Règles § 8.1 + revue § 8.2 | oui (+ Guide) |
| 5 | Typage à l'import § 8.3 | oui (+ Guide) |
| à part | Ménage marques : retirer « SMEG » collé dans 1 331 réf. ; vérifier Concord/Concorde | données |

Le lot 2 dépend de la création du type sur le site (action client).

---

## 11. Critères d'acceptation et zéro régression

- Avant/après chaque lot : nombre d'appareils par type, comparé ; tout écart non prévu = arrêt.
- Lot 2 : les exports d'un échantillon de fiches hors du nouveau type sont **identiques** octet pour octet (métas, titres, CSV).
- Tests unitaires du moteur sur les cas pièges : `HM633GBS1` (combiné) vs ancienne `HM…` (cuisinière) ; `AKZ9S8270NB` (vapeur) vs `AKZ513IX` (four) ; `AWE8230ZEN` (lave-linge malgré le Z) ; `GO4W264` (Candy, lavante) vs `H3W 69TME` (Hoover, lave-linge).
- Test de charge : découverte complète < 30 s sur 720 000 appareils (mesuré 15 s en script).
- Rejouer les tests avec le style global (piège eventFilter) et `compileall`.

---

## 12. Questions ouvertes

1. Nom exact du nouveau type : « Four combiné micro-ondes » (proposé, terme Neff/Gaggenau) ou autre libellé déjà prévu côté site ?
2. Règles § 9.2 issues de la seule découverte (sans source web) : validées d'office ou une par une ?
3. Acceptation groupée des propositions « fortes » d'une règle : autorisée ?
4. Les ~115 lignes typées accessoire (Porte, Panier, Rails, Filtre, Accessoires) : hors sujet ici, à traiter à part ?
