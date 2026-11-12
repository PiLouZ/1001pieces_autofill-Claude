# Cahier des charges — Reprise des fiches produit du site 1001pieces.com

**Statut :** En cours — conception validée le 2026-11-10 ; étape 1 (lecteur de description, `src/utils/lecteur_fiche/`), étape 2 (rapprochement, `src/utils/rapprochement_fiche/`) et étape 3 (aperçu et enregistrement d'une fiche) réalisées le 2026-11-12
**Version :** 1.0
**Contexte :** le site 1001pieces.com (PrestaShop) contient des milliers de fiches produit qui listent les appareils compatibles et les relations entre pièces (remplacements, équivalences). Une partie de ces fiches a été produite par l'outil (export « Fiche complète »), une autre a été écrite à la main dans le back-office. Ce document définit comment reprendre ces données dans l'outil, puis comment l'outil devient la passerelle qui alimente le site.

L'outil CompatsRadar (artefact du technicien) a servi de point de départ : il lit la même liste « Appareils employant cette pièce », mais dans l'autre sens (description → compatibilités EveryParts). Ses règles de lecture (formats de références, groupes de marques, normalisation de la ponctuation) sont réutilisées ici.

---

## 1. Objectifs

- Reprendre dans l'outil, en une fois, le contenu des fiches du site : pièces, appareils compatibles, remplacements, équivalences, EAN.
- Ensuite, lire une fiche à la demande à partir de son lien, pour les fiches modifiées directement dans le back-office.
- Ne rien écraser ni supprimer : l'import **ajoute** des données. Tout doute est **validé par l'utilisateur**.
- Faire de l'outil la référence pour les appareils, les compatibilités et les relations entre pièces, puis régénérer les descriptions du site avec les gabarits « Fiche complète ».

- Garder, pour chaque pièce reprise du site, **la référence produit interne** du site, pour que l'export EveryParts se fasse sans ressaisie (§ 5.8).

**Hors périmètre :** un nouveau format d'export EveryParts (l'export actuel des compatibilités suffit, car EveryParts crée les appareils à la volée ; il est seulement pré-rempli, § 8.2) et ServiceNet (portail Whirlpool, cité seulement comme illustration).

---

## 2. Volumes mesurés (2026-11-10)

| | Site PrestaShop | Outil |
|---|---|---|
| Produits ou pièces | 13 303 (13 090 actifs) | 5 856 pièces réelles |
| Descriptions avec liste d'appareils | 9 187 | — |
| Descriptions avec « Remplace les références » | 2 946 | 2 363 remplacements |
| Descriptions avec « Références équivalentes » | 740 | 163 groupes, 754 références |
| Liens pièce → appareil | 6 956 846 (table EveryParts, 4 224 produits) | 5 081 891 |
| Appareils par produit, en moyenne | ≈ 1 650 | ≈ 870 |
| Appareils | — | 717 250 |

Conséquences :
- Pour environ 5 000 produits, la description est la **seule** source de compatibilités : il n'y a pas de lien dans la table du site.
- La base de l'outil (≈ 1 Go) peut atteindre 1,5 à 2 Go. Le premier lot sert de mesure avant de lancer la suite (§ 7.4).
- Un lot de 100 produits représente environ 165 000 lignes d'appareils : la validation se fait par catégorie de cas, pas ligne par ligne (§ 7).

---

## 3. Sources

### 3.1 Export SQL PrestaShop — reprise initiale

L'utilisateur a accès à la base du site. Deux exports CSV (séparateur `;`, champs entre `"`, en-têtes en première ligne), triés par `id_product` :

- **Produits** (`emg_product`, `emg_product_lang` avec `id_lang = 1`, `emg_manufacturer`, `emg_category_lang`) : `id_produit`, `reference`, `nom_produit`, `marque`, `ean`, `categorie`, `actif`, **`description`**.
- **Compatibilités** (`emg_ukooparts_compatibility`, `emg_ukooparts_engine`, `emg_ukooparts_manufacturer`, `emg_ukooparts_engine_type_lang`) : `id_produit`, `reference_appareil`, `modele_appareil`, `marque_appareil`, `type_appareil`.

Les relations entre pièces (remplacements, équivalences) n'existent **que dans la description**. L'export des compatibilités ne suffit donc pas.

### 3.2 Lien d'une fiche — au fil de l'eau

La page publique d'une fiche contient tout ce qu'il faut, sans accès à la base :
- la **description** balisée (§ 4.1) ;
- la **table des compatibilités** EveryParts (bloc `ucpt-table`), quand elle existe : type, marque, `réf - nom` pour chaque appareil. La page n'en affiche que **la première page** (20 lignes ; 92 pages pour le produit 7285) : le reste est chargé à la demande. La table complète vient donc de l'export SQL des compatibilités (§ 3.1) ; le lecteur relève le nombre de pages et signale une table incomplète ;
- la **catégorie** du produit dans les métadonnées (par exemple « Pompe de vidange - Lave-linge ») ;
- la **référence produit interne**, dans le bloc `.product-reference` (`<span class="js-product-reference">EL1113161010</span>`) et dans les métadonnées (`sku`, `mpn`), ainsi que l'**EAN** (`gtin13`) quand il existe ;
- l'**`id_product`** PrestaShop, au début du nom de la page (`…/20746-regulateur-de-debit-….html`).

Il est aussi possible de coller la description (le HTML du back-office ou le texte).

### 3.3 Un seul lecteur

Les deux sources passent par **le même lecteur de description**. Il n'y a ainsi qu'une seule règle de lecture à maintenir.

---

## 4. Lecture d'une description

### 4.1 Structure actuelle des fiches

```html
<h2 class="class_perso1">Pompe de vidange … <span class="class_perso6">(photos non contractuelles)</span></h2>
<div class="class_perso2">Compatible avec <a href="#Balay">Balay</a> <a href="#Bauknecht">Bauknecht</a> …</div>
<div class="class_perso3">Code produit : 481073071153 C00319033</div>
<div class="class_perso3 class_perso6">Remplace les références : C00535957 488000535957 C00309416 482000032568</div>
<div class="class_perso3 class_perso6">Références équivalentes : 00145522</div>
<div class="class_perso3 class_perso6">Références équivalentes : 481949</div>
<div class="class_perso4">Appareils compatibles :</div>
<div class="class_perso5">
  <div id="Balay"><b><u>Balay</u></b></div>
  <div>3TL865/02 - 3TL865</div>
  …
</div>
```

| Bloc | Contenu | Rangement dans l'outil |
|---|---|---|
| `Compatible avec` | liste des marques | indice pour reconnaître les marques (§ 4.4), rien n'est enregistré |
| `Code produit` | 1 à 3 références | la 1ʳᵉ = la pièce, les suivantes = équivalentes (§ 5.1) |
| `Remplace les références` | anciennes références | remplacements vers la pièce (§ 5.4) |
| `Références équivalentes` | une ligne par origine | groupe d'équivalence avec étiquette d'origine (§ 5.3) |
| Titre de la liste | « Appareils compatibles : », anciennement « Appareils employant cette pièce », autres variantes possibles | début de la liste |
| Marque | `<div id="…">` | constructeur des lignes qui suivent |
| Ligne `RÉF - NOM` | réf. modèle et nom commercial | appareil (§ 5.2) |

### 4.2 Lecture guidée par les gabarits

- Les gabarits « Fiche complète » de l'outil (`code_produit_template`, `remplace_template`, `equivalentes_template` dans la section `fiche` de la configuration des exports) servent **aussi** de modèles de lecture : le texte qui entoure `{reference}` ou `{references}` devient le repère.
- **Tous les profils Fiche enregistrés** sont essayés. Chacun reçoit un score, égal au nombre de blocs reconnus (code produit, remplace, équivalentes, titre de liste), et le meilleur l'emporte.
- En cas d'égalité, ou si aucun profil ne reconnaît l'essentiel, l'utilisateur choisit dans l'aperçu. L'outil se rabat alors sur le **repérage par texte** (libellés « Code produit : », « Remplace les références : », titres de liste connus), sur le modèle de CompatsRadar.
- Si un gabarit est modifié, l'export **et** la lecture suivent ensemble. Il n'y a pas de réglage de lecture séparé.

### 4.3 Normalisation avant comparaison

La fiche et les gabarits sont réduits à la même forme avant d'être comparés :
- **on garde** le découpage en blocs (`div`, `p`, `br`), les classes et le texte ;
- **on ignore** les balises de mise en forme (`b`, `u`, `strong`, `em`, `span`) et les attributs `style` ;
- les espaces multiples et les `&nbsp;` sont ramenés à un seul espace.

Les variantes de mise en forme (gras en balise ou en CSS inline) n'ont donc aucun effet sur la lecture.

### 4.4 Reconnaître une marque

On ne s'appuie pas sur le gras, mais sur un faisceau d'indices :
- un bloc sans ` - ` ;
- dont le texte figure dans la ligne « Compatible avec » ou parmi les marques connues de la base ;
- ou qui porte un `id`.

Une marque inconnue est un doute.

### 4.5 Lignes d'appareils

- Le format actuel est `RÉF - NOM`.
- Les formats anciens restent reconnus : Bosch-Siemens `RÉF/01 NOM`, et numéros PNC Electrolux de 8 à 13 chiffres alignés sur une ligne. Ce sont les règles de CompatsRadar.
- Les noms commerciaux tronqués (`ITW A 51052 W1 (DE`) ou de casse variable (`WATEco10Di` / `WATECO10DI`) sont lus tels quels. Ils ne servent pas à identifier l'appareil (§ 5.2).

### 4.6 Liste tronquée

Une fiche exportée par l'outil peut avoir une liste d'appareils réduite par la limite de caractères (`max_caracteres`). Le lecteur doit repérer une liste coupée, pour ne pas en tirer de faux « absents » (§ 6.2).

---

## 5. Rapprochement avec la base

### 5.1 Identité de la pièce

- `ref_piece` = **la 1ʳᵉ référence du « Code produit »**.
- `p.reference` (PrestaShop, la référence produit interne, § 5.8) sert de secours quand la ligne manque. Elle porte souvent un **préfixe** (`EL1113161010`, `GAU11051894`) : la comparaison avec le code produit se fait **préfixe retiré**, à partir d'une liste de préfixes connus tenue en configuration. Un écart qui subsiste est un doute.
- Les références suivantes du « Code produit » (Indesit, Beko…) sont **équivalentes** à la pièce. Elles n'ont pas forcément la même liste d'appareils : **la liste de la fiche s'attache à la pièce principale seule**.
- Une pièce présente en base comme **fantôme** (`is_phantom = 1`) devient une pièce réelle quand elle correspond à un produit du site. Ses liens hérités ne changent pas.
- **EAN :** rangé avec le produit du site (§ 5.8), et non sur la pièce. C'est une donnée commerciale, donc le site fait foi :

| Situation | Action |
|---|---|
| EAN vide dans l'outil | rempli depuis le site |
| même EAN | rien |
| EAN différent | doute |
| clé de contrôle EAN-13 fausse | signalé, non enregistré |

Ranger l'EAN avec le produit règle le cas des génériques : l'EAN du produit 7285 (`8015250275551`) est celui du **produit vendu**, sans rien affirmer sur la pièce d'origine `481073071153`.

### 5.2 Appareils

Un appareil est cherché par **marque + réf. modèle**, en deux passes : **ponctuation considérée**, puis **ponctuation ignorée**. La normalisation retire les espaces, tirets, `/`, `.` et `_`, met la référence en majuscules et suit la casse des marques de l'outil. Les deux passes sont nécessaires :
- ne considérer que l'écriture exacte **créerait des doublons** : `WOR 20154/02` serait un nouvel appareil à côté de `WOR20154/02` ;
- n'utiliser que la forme normalisée **fusionnerait des appareils distincts** qui ne diffèrent que par la ponctuation.

**Mesure dans la base (2026-11-12) :** 467 références normalisées correspondent déjà à plusieurs écritures, soit 937 appareils sur 717 250. Le plus souvent, c'est la présence ou l'absence de `/` (354 cas : `MBW61SW/1` / `MBW61SW1`), puis les espaces (63), les tirets (41 : `FN4957SED-1` / `FN4957SED1`) et des fautes (`CHW200G` / `CHW200G.`, `BBS2451FF//02`). Certains de ces cas sont de vrais doublons, d'autres peut-être pas. Seul l'utilisateur peut trancher.

| Niveau | Règle | Traitement |
|---|---|---|
| Exact | marque et réf. modèle identiques, ponctuation comprise, **un seul** candidat | lié |
| Exact multiple | même réf. exacte portée par plusieurs appareils (cas des décisions `DISTINCT` de `reference_decisions`) | départage par le type (§ 5.6), sinon doute |
| Normalisé | pas de correspondance exacte, **un seul** candidat à la ponctuation près, pas de décision contraire | proposé, validable en bloc dans le résumé ; l'écriture de la base est gardée |
| Normalisé ambigu | plusieurs écritures en base pour la même forme normalisée | doute : l'utilisateur choisit l'appareil, ou signale un doublon existant |
| Déjà couvert | l'appareil est déjà lié à une autre référence de la lignée de la pièce (prédécesseur, successeur ou équivalente) | **pas de nouveau lien** ; rattachement direct possible sur demande dans l'aperçu |
| À valider | référence trouvée sous une autre marque du groupe ou un autre type, ou seulement par le nom commercial | l'utilisateur choisit |
| Absent | aucun candidat, ni exact ni normalisé | création de l'appareil, validée dans l'aperçu |

- **Pas de création si un candidat normalisé existe.** Un appareil n'est créé que si les deux passes échouent : c'est ce qui empêche les doublons.
- **Les décisions sont mémorisées.** Quand l'utilisateur dit qu'une écriture est « le même appareil » ou « un appareil distinct », la décision est gardée pour la paire d'écritures et n'est plus redemandée. La table `reference_decisions` existante porte sur une **même** référence exacte partagée par plusieurs appareils (2 117 décisions `DISTINCT`) : il faut une mémoire du même genre pour les **paires d'écritures** (§ 9).
- **Doublons existants :** les 467 cas déjà en base ne sont pas corrigés par l'import. Ils apparaissent en « normalisé ambigu » quand une fiche les touche, et leur nettoyage passe par l'outil de doublons existant.
- **Le nom commercial n'est jamais écrasé** à partir d'une fiche.
- La lignée se calcule **une fois par fiche** (chaîne de remplacements et groupe d'équivalence), et non une fois par appareil.

Cas observé : la fiche BSH `11051894` liste 450 appareils. Dans l'outil, ce sont exactement les liens de ses 4 prédécesseurs (306 + 2 + 20 + 122). Ils sont tous « déjà couverts » : rien n'est ajouté.

### 5.3 Équivalences et étiquette d'origine

- **Un seul groupe d'équivalence par pièce**, comme aujourd'hui : l'outil fusionne les groupes et l'équivalence se propage.
- Chaque membre du groupe reçoit une **étiquette d'origine**, par exemple « BSH ». L'outil mémorise aussi **la ligne de la fiche** d'où vient la référence. Les lignes peuvent ainsi être réécrites à l'identique, même sans étiquette.
- L'étiquette est **déduite du format** de la référence (§ 5.5). Sinon, elle est **saisie dans l'aperçu**.
- Une référence reconnue comme une erreur peut être **écartée**. Elle est consignée comme telle et n'est plus proposée. Exemple : `481949` sur la fiche de la pompe 481073071153.

Il faut donc ajouter une colonne d'origine (et le numéro de ligne) sur `piece_equivalence_groups`, vide pour les 754 références existantes.

### 5.4 Remplacements

« Remplace les références : X Y » signifie X → pièce et Y → pièce. Les anciennes références absentes de la base sont créées comme fantômes, comme aujourd'hui.

En cas de conflit (X a déjà un autre successeur Z) :
1. **vérifier la chaîne** (`get_supersession_chain`) : si la pièce de la fiche se trouve plus loin dans la chaîne de Z, la fiche confirme la lignée et il n'y a pas de conflit ;
2. sinon, c'est un **doute** : l'aperçu propose de garder l'existant ou de prendre la fiche.

Entre paires Whirlpool/Indesit, le remplacement se fait **terme à terme** : `481244019535 → 481244010747` et `C00338369 → C00314482`. On ne croise jamais les marques. L'appariement s'appuie sur la forme des références (§ 5.5), pas sur leur position dans la ligne.

### 5.5 Table des formats de références

La table est tirée des pièces de la base (marque dominante des appareils liés). Elle est validée dans les grandes lignes et doit vivre **en configuration**, modifiable sans PR. Les règles sont appliquées de la plus précise à la plus large : la première qui correspond l'emporte.

| Motif | Origine |
|---|---|
| `48` + 10 chiffres | Whirlpool |
| `C00` + 6 chiffres | Indesit (groupe Whirlpool) |
| `00` + 6 chiffres | BSH (ancien format) |
| 8 chiffres commençant par `10`, `11`, `12`, `17`, `20` | BSH |
| 8 chiffres commençant par `41`, `43`, `49`, `70`, `91`, `92`, `93` | Candy (Hoover, Rosières) |
| 10 chiffres commençant par `17`, `18`, `28` | Beko |
| 10 chiffres, autres débuts | Electrolux |
| 11 chiffres commençant par `50`, 12 chiffres commençant par `14` | Electrolux |
| 9 chiffres commençant par `61`, `71`, `74`, `95` | Liebherr |
| 9 chiffres commençant par `69`, `75`, `81` | Smeg |
| 7 chiffres | Miele |
| 6 chiffres commençant par `0` | Atlantic / Thermor |
| 2 chiffres + `X` + 4 chiffres (`92X6108`, `31X1354`), `AS` + 7 chiffres | Brandt (De Dietrich, Sauter, Fagor) |
| `DD82-…`, `DA97-…`, `DC31-…` | Samsung |
| 3 lettres + 8 chiffres | LG |

La base compte 407 références Brandt de la forme « 2 chiffres + `X` + 4 chiffres », et 2 avec un `S` à la place du `X` (`71S7962`, `71S8574`), à confirmer.

Cas mélangés, donc des doutes : 10 chiffres commençant par `15` (Electrolux ou Beko), 8 chiffres commençant par `42` (Candy ou Sharp), 8 chiffres commençant par `32` (Sharp ?), 9 chiffres commençant par `16` ou `26` (Beko ?).

**Apprentissage :** les choix de l'utilisateur sur les cas inconnus sont consignés, comme le font déjà `reference_decisions` et `refus_completions`. Une série de choix identiques sur une même forme devient une **règle proposée**, ajoutée à la table seulement après validation.

### 5.6 Type d'appareil

La description ne donne pas le type, et certaines fiches mélangent plusieurs types. Le type se décide **appareil par appareil** :
1. la table des compatibilités du site (`type_appareil`) ;
2. l'appareil déjà en base (même marque et même réf. modèle). Si la base le connaît sous deux types, c'est un doute ;
3. la catégorie du produit, seulement si elle désigne un seul type sans ambiguïté (table de correspondance catégorie → type) ;
4. sinon, c'est un doute, regroupé par fiche dans le résumé.

### 5.7 Provenance des liens

Les liens pièce → appareil sont **l'union** de la description et de la table du site. Une nouvelle colonne de provenance sur `piece_associations` prend la valeur « description », « table du site » ou « les deux ». Elle reste vide pour les liens existants (PDF, CSV, saisie). Un lien déjà présent ne crée pas de doublon (`UNIQUE(piece_id, appareil_id)`) : seule sa provenance est complétée.

### 5.8 Produit du site et référence interne

Chaque pièce reprise du site garde en mémoire **le produit du site qui la vend** :

| Donnée | Source export SQL | Source page | Exemple |
|---|---|---|---|
| Référence produit interne | `p.reference` | `.product-reference`, `sku` | `EL1113161010` |
| `id_product` : identifiant du produit **sur le site 1001pieces.com** (PrestaShop) | `p.id_product` | début du nom de la page | `20746` |
| EAN | `p.ean13` | `gtin13` | `7321423021278` |
| Date de la dernière lecture | date de l'export | date de lecture | — |

Exemples observés :

| Produit | Code produit (= `ref_piece`) | Référence interne |
|---|---|---|
| 7285 | `481073071153` | `481073071153` (sans préfixe) |
| 20746 | `1113161010` | `EL1113161010` |
| 20744 | `11051894` | `GAU11051894` |

Règles :
- L'`id_product` est **l'identifiant du site**. Il ne faut le confondre ni avec l'`id` interne des pièces de l'outil, ni avec les identifiants d'appareils EveryParts (`id_ukooparts_engine`, l'`id_appareil` de CompatsRadar). Le module EveryParts étant installé dans le PrestaShop du site, c'est ce même `id_product` qui désigne le produit dans les compatibilités EveryParts.
- La référence interne est toujours **lue** sur le site, jamais reconstruite à partir d'un préfixe. Le préfixe varie et n'est pas déductible de façon sûre.
- Elle se rattache à la **pièce principale** (1ʳᵉ réf. du code produit). Les équivalentes et les fantômes n'ont pas de produit, sauf s'ils sont eux-mêmes vendus sur le site.
- **Une pièce peut avoir plusieurs produits** : par exemple une pièce d'origine et un générique, qui citent le même code produit. D'où une petite table dédiée plutôt qu'une colonne sur `pieces` (§ 9). Une référence interne n'appartient qu'à **une** pièce : si elle change de pièce à la relecture, c'est un doute.
- Données commerciales : **le site fait foi** (§ 6.1). Une référence interne qui change sur le site met à jour l'outil, avec signalement dans l'aperçu.
- Une pièce saisie dans l'outil sans produit sur le site n'a pas de référence interne. L'export EveryParts garde alors la saisie manuelle actuelle (§ 8.2).

---

## 6. Qui fait foi, relecture

### 6.1 Partage

| Donnée | Fait foi |
|---|---|
| Appareils, compatibilités, remplacements, équivalences | l'outil |
| Nom du produit, prix, stock, catégorie, EAN, référence interne, `id_product` | le site |

### 6.2 Relire une fiche déjà importée

- L'outil **ajoute seulement**.
- Les liens présents dans l'outil mais absents de la fiche sont **signalés pour information**, sans proposition de retrait. Seuls les liens de provenance site sont concernés, et rien n'est signalé si la liste de la fiche est tronquée (§ 4.6).
- Une fiche produite par l'outil et non modifiée depuis ne doit rien apporter : sa relecture sert de contrôle de cohérence.

---

## 7. Aperçu et import en masse

### 7.1 Fiche seule

Aperçu complet ligne à ligne, avec les niveaux du § 5.2, les relations (§ 5.3, 5.4) et les doutes. Rien n'est écrit avant validation.

### 7.2 Import en masse

- **Lots de 100 produits** (réglable), dans l'ordre de `id_produit`.
- Chaque lot s'ouvre sur un **résumé par catégorie** : exacts, normalisés, déjà couverts, à valider, absents, conflits, types manquants, profils ambigus. Chaque catégorie se valide **en bloc**.
- Le **détail complet** reste accessible, avec des filtres par niveau, type de relation et provenance, dans la vue virtuelle existante.

### 7.3 Reprise

- L'outil mémorise le dernier `id_produit` traité et la date de l'export : on peut fermer l'application et reprendre au lot suivant.
- Un export plus récent est détecté : l'outil propose de repartir de zéro ou de continuer.
- Relancer un lot ne crée pas de doublon.

### 7.4 Premier lot de mesure

Le premier lot sert à mesurer la part de liens déjà en base, la part de doutes et la croissance réelle de la base. Le rythme des lots suivants se décide à partir de ces chiffres.

### 7.5 Passage par l'existant

Le tout passe par le tronc commun d'import et par `EventDrivenSaveService` (conventions du projet).

---

## 8. Retour vers le site et EveryParts

### 8.1 Description du site

L'export « Fiche complète » (`src/utils/fiche_produit_generator.py`) produit déjà le format du site. Il reste deux écarts à combler :
1. **une ligne « Références équivalentes » par origine**, alors qu'elles sont aujourd'hui toutes sur une ligne (`toutes_equivalentes`). On regroupe par étiquette, puis par ligne mémorisée ;
2. **la paire dans le code produit**, par exemple `481073071153 C00319033`, alors que le gabarit n'en porte aujourd'hui qu'une (`{reference}`).

La structure reste modifiable par les gabarits, comme pour les exports HTML. Les références écartées (§ 5.3) disparaissent de la fiche régénérée.

### 8.2 Export EveryParts

Aujourd'hui, la colonne `product` du CSV EveryParts vaut `{export_ref}` : la référence saisie ou confirmée dans le dialogue d'export (`ExportManager._handle_single_reference_dialog`), qui propose par défaut le terme recherché (par exemple `1113161010`). L'utilisateur doit taper `EL1113161010` lui-même.

Avec la référence interne en mémoire (§ 5.8) :
- le dialogue **propose la référence interne** du produit de la pièce. Elle reste modifiable ;
- si la pièce a **plusieurs produits**, le dialogue propose de choisir le produit ;
- s'il n'y en a aucun, le comportement actuel est conservé ;
- la recherche par une ancienne référence (lignée) propose la référence interne de la **pièce courante**. Exemple : rechercher `00703010` propose `GAU11051894` ;
- une nouvelle variable de gabarit `{ref_interne}` (et `{id_product}`) est disponible dans la configuration des colonnes et du nom de fichier CSV. Le format par défaut ne change pas.

---

## 9. Évolutions du modèle de données

Toutes les colonnes sont nullables et sans valeur par défaut calculée : leur ajout est instantané sous SQLite, même sur 5 millions de lignes.

| Table | Ajout |
|---|---|
| nouvelle `produits_site` | `ref_interne` (unique), `id_product`, `ref_piece` (pièce principale), `ean`, date de dernière lecture |
| `piece_associations` | provenance du lien |
| `piece_equivalence_groups` | étiquette d'origine, n° de ligne de la fiche |
| nouvelle | état de la reprise (dernier `id_produit`, date de l'export) — étape 4 |
| nouvelle | décisions sur les formats et références écartées |
| nouvelle | décisions sur les paires d'écritures d'appareils (marque, écriture A, écriture B, « même » ou « distinct ») |
| configuration | table des formats, correspondance catégorie → type, préfixes de référence interne, groupes et alias de marques : `data/reprise_fiches.json` (défauts dans `src/utils/rapprochement_fiche/configuration.py`, copie dans `data/reprise_fiches.example.json`) — **fait à l'étape 2** |

`produits_site.ref_piece` suit les renommages de pièce comme les autres tables à référence texte (`piece_supersessions`, `piece_equivalence_groups`).

---

## 10. Découpage proposé

Chaque étape peut être testée seule :
1. **Lecteur de description** : normalisation, gabarits, repérage par texte. Il n'écrit rien en base et se vérifie sur les 9 187 descriptions du site (part lue correctement, variantes de balises rencontrées).
2. **Rapprochement** avec la base : niveaux, lignée, formats, type.
3. **Aperçu et enregistrement** d'une fiche, avec les colonnes du § 9.
4. **Import en masse** par lots, résumé, reprise.
5. **Export** : une ligne par origine, paire dans le code produit, référence interne proposée dans l'export EveryParts.

### 10.1 Mesure de l'étape 1 (2026-11-12)

Mesure sur l'export complet du site (13 302 produits, `scripts/mesurer_lecteur_fiches.py`, marques et types de la base en lecture seule) :
- 12 228 descriptions avec une liste, 6 454 931 lignes d'appareils. **10 867 (88,9 %) sont lues sans aucun doute de lecture** : code produit trouvé, au moins un appareil, aucun bloc non lu, aucune marque inconnue.
- Les doutes restants sont surtout des en-têtes de série pris pour des marques (« Lave-linge SIWAMAT », « HOTTE DECOR », 456 fiches) et 139 blocs d'en-tête qui parlent de références sans format reconnu.
- **Formats anciens rencontrés**, désormais reconnus :
  - « Montage sur … » pour « Compatible avec » ;
  - une vingtaine de titres de liste (« Appareil(s) employant ce thermostat », « utilisant ce filtre », « comaptibles »…) ;
  - « Remplace les produits suivants » ;
  - « Remplacé par » (le successeur) ;
  - références par marque (« Référence EGO : … », « Bosch Réf. fabricant : … », 174 fiches) ;
  - 12NC suivi du nom ;
  - type écrit en fin de ligne ou sur la ligne suivante.
- **Pour l'étape 2 :**
  - 1 635 fiches n'ont pas d'en-tête de marque et annoncent plusieurs marques, souvent un groupe (« Whirlpool Laden Ignis Bauknecht ») : la marque de chaque ligne se déduit au rapprochement ;
  - 412 fiches ne prennent leurs marques que dans la marque du produit ;
  - références internes : 2 029 égales au code produit, 5 524 préfixées (FAR, EL, GAU, ROS, MIE, LH, ATC, D, NOT, BEO, CET, STN0…), 4 637 différentes, dont 1 106 désignent une référence de la lignée (remplacée ou équivalente) et la plupart des autres sont des codes de fournisseur (`ES10028`…).
- 761 listes sont probablement réduites : replis de l'export de l'outil, dernière marque vide, ou points de suite.

### 10.2 Rapprochement — étape 2 (2026-11-12)

`src/utils/rapprochement_fiche/` : `rapprocher(lecture, acces, config, page=…)` rend, **sans rien écrire** (base ouverte en `mode=ro`), un `Rapprochement` :
- **identité** : pièce (réelle, fantôme, absente), référence interne égale / préfixée / de la lignée / différente (doute), EAN vérifié ;
- **appareils** : deux réponses par ligne. Le **niveau** d'identification (exact, exact multiple, normalisé, normalisé ambigu, à valider, absent) et le **lien** : *déjà lié* (lien présent sur la pièce elle-même, cas de 20746), *déjà couvert* (autre référence de la lignée, cas de 20744), *nouveau*. Union avec la table du site (provenance description / table / les deux), type appareil par appareil (table, ligne, base, catégorie) ;
- **remplacements** (nouveau, déjà présent, confirmé par la chaîne, conflit, cycle) avec appariement par la forme dans une paire, et « Remplacé par » ;
- **équivalences** (nouveau, déjà dans le groupe, fusion de groupes, déjà dans la succession, écartée) avec étiquette d'origine déduite du format ;
- **doutes regroupés par catégorie** (`CATEGORIES_DOUTES`), et `resume()` pour l'aperçu.

Choix faits à cette étape :
- un appareil dont l'écriture exacte existe mais dont la forme normalisée a **plusieurs écritures en base** ressort en « normalisé ambigu », avec l'écriture exacte proposée : les 467 collisions de la base ressortent toutes ainsi (test sur une copie de la base) ;
- « à valider » couvre la même réf. sous **une autre marque du groupe** (groupes en configuration, liste de départ), un **type explicite** (table, ligne) contraire à la base, et la correspondance par le **seul nom commercial** ;
- marque d'une ligne sans en-tête : déduite quand **une seule** des marques annoncées porte la référence (exacte, puis normalisée) ; singulier/pluriel toléré (« Rosière » / « Rosières ») et alias en configuration ;
- les mémoires du § 9 (décisions sur les paires d'écritures, références écartées) sont déjà prises **en paramètre** : leurs tables viennent à l'étape 3.

Vérification : fiches d'exemple sur un extrait de la vraie base (`tests/fixtures/fiches_site/base_extrait.sql`, `scripts/extraire_base_fiches_test.py`) : 20746 → 831 déjà liés ; 20744 → 450 déjà couverts (306 + 2 + 20 + 122), pièce fantôme ; 7285 → 481… → 481…, C00… → C00…, `481949` en doute d'origine.

**Mesure** (`scripts/mesurer_rapprochement_fiches.py`, 1 produit sur 10 de l'export, 1 298 fiches, 700 521 lignes, copie de la base ; médiane 2 ms par fiche, 1,6 s au plus quand l'index d'une grosse marque se charge) :

| Niveau | Lignes | Part |
|---|---|---|
| exact | 560 068 | 80,0 % |
| absent (création) | 128 893 | 18,4 % |
| à valider | 6 309 | 0,9 % |
| normalisé | 2 782 | 0,4 % |
| exact multiple | 1 647 | 0,2 % |
| normalisé ambigu | 822 | 0,1 % |

- Liens : 64,5 % nouveaux, 21,5 % déjà liés, 12,9 % déjà couverts par la lignée, 1,1 % à décider.
- **Lignes sans en-tête de marque** : 25 462 dans 173 fiches. La marque est déduite pour 62,9 % d'entre elles, et pour **90,7 % de celles qui existent en base** ; les autres sont des absents (marque à choisir pour la création) ou des références trouvées sous plusieurs marques.
- 71,3 % des fiches n'ont aucun doute sur les appareils. Pièces : 80,2 % absentes de l'outil, 18,8 % réelles, 1,0 % fantômes.
- Référence interne : 41,1 % « différente » (doute ; surtout des codes fournisseur), 37,6 % préfixée, 16,5 % égale, 4,6 % de la lignée.
- Remplacements : 74,3 % nouveaux, 22,8 % déjà présents, 2,0 % confirmés par la chaîne, 9 conflits et 1 cycle. Équivalences : 91,9 % nouvelles.
- Doutes les plus fréquents (en fiches) : référence interne différente (534), lecture (336), à valider (221), marque à choisir (150), origine inconnue (112).

### 10.3 Aperçu et enregistrement — étape 3 (2026-11-12)

- **Modèle (§ 9)** : `src/data/_db_mixins/fiches_site.py`. Tables `produits_site` (`ref_interne` clé, `id_product`, `ref_piece`, `ean`, `lu_le`), `decisions_ecritures` (clé de marque, écritures A < B, `meme` / `distinct`), `decisions_references` (`ref_piece`, référence, `ecartee` / `origine`, étiquette, forme de la référence pour l'apprentissage du § 5.5) ; colonnes `piece_associations.provenance`, `piece_equivalence_groups.origine` et `.ligne_fiche`. Le renommage et la suppression d'une pièce suivent `produits_site` et `decisions_references` ; la fusion de groupes garde les origines (UPDATE du `group_id`). L'état de la reprise (§ 7.3) est laissé à l'étape 4.
- **Migration** sur une copie de la vraie base (API backup, 5 083 744 liens) : **0,01 s**, taille inchangée (999,7 Mo) ; toutes les colonnes nouvelles sont vides pour l'existant.
- **Mémoires** : `rapprocher(…, memoires=True)` lit les décisions consignées (paires d'écritures, références écartées, étiquettes choisies) et compare la fiche à l'outil : EAN (à remplir / identique / différent = doute), référence interne déjà rattachée à une autre pièce (doute), référence interne changée sur le site pour le même `id_product` (mise à jour signalée), libellé de la pièce. Une ligne « à valider » dont **un seul** candidat est déjà lié à la pièce reprend ce choix sans le redemander. Les liens de provenance site absents de la fiche sont listés (`absents_de_la_fiche`), sauf liste tronquée.
- **Libellé** (décision du 2026-11-12) : le titre de la fiche, sans « (photos non contractuelles) », devient le libellé d'une pièce qui n'en a pas ; un libellé différent est un doute (garder par défaut, ou prendre la fiche).
- **Décisions et plan** (`src/utils/rapprochement_fiche/decisions.py`, sans Qt) : chaque élément appartient à une catégorie du résumé (exacts, normalisés, déjà couverts, à valider, absents, types manquants, remplacements et équivalences, conflits), validée en bloc, laissée de côté (rien n'est écrit, elle revient à la relecture) ou en attente. Un choix individuel l'emporte. Un élément validé sans proposition possible (appareil parmi plusieurs, création sans marque ou sans type) est « à compléter ». Rien ne s'enregistre tant qu'une catégorie est en attente ou qu'une ligne est à compléter. Choisir un appareil d'une autre écriture consigne « même » ; créer malgré une écriture proche consigne « distinct ».
- **Enregistrement** (`EnregistrementFicheService`) par les briques du tronc d'import : `ImportManager._batch_insert_devices` pour les appareils, `import_relations.apply_relations` pour les remplacements (fantômes, obsolescence) et les équivalences (libellé propagé), invalidation des caches comme après un import, puis `EventDrivenSaveService.save_after_import`. Propres à la reprise : pièce fantôme → réelle, liens avec provenance (un lien présent ne fait que compléter sa provenance), origines, produit du site, décisions.
- **Aperçu** : `src/ui/fiche_site_dialog.py`, menu Données → « Lire une fiche du site… » (lien téléchargé hors du thread principal, ou description collée).
- **Vérification** (`tests/unit/test_enregistrement_fiche.py`, sans réseau) : les 3 fiches d'exemple enregistrées puis relues sans rien ajouter, sur l'extrait **et** sur une copie de la vraie base (`scripts/mesurer_migration_fiches.py --fiches`) ; 20744 : la fantôme devient réelle, aucun nouveau lien ; 20746 : 831 provenances complétées, aucun lien créé ; 7285 : pièce créée avec le titre pour libellé, remplacements terme à terme, origines BSH / Indesit et n° de ligne, `481949` écartée puis plus proposée.

---

## 11. Fiches d'exemple

| Produit | Intérêt |
|---|---|
| 7285, pompe de vidange Whirlpool / Indesit (générique) | paire en code produit, remplacements, 2 lignes d'équivalentes dont une erreur, 16 marques, table du site présente |
| 20746, régulateur de débit Electrolux | une seule référence, PNC, aucune table du site ; 831 lignes = 831 liens en base (fiche produite par l'outil) |
| 20744, balconnet BSH | pièce fantôme en base, 4 remplacements ; 450 lignes = union des prédécesseurs |

---

## 12. Décisions arrêtées

| Sujet | Décision |
|---|---|
| Source | export SQL pour la reprise, lien de fiche ensuite |
| ServiceNet, EveryParts | hors périmètre |
| Pièce principale | 1ʳᵉ réf. du code produit, `p.reference` en secours |
| Liste d'appareils | sur la pièce principale seule |
| Équivalences | un groupe, étiquette d'origine déduite du format, saisie en secours |
| Appareils | union description et table, avec provenance |
| Type | par appareil : table, base, catégorie, doute |
| Identité d'un appareil | marque + réf. modèle, ponctuation considérée puis ignorée ; pas de création si un candidat normalisé existe ; décisions mémorisées |
| Remplacements | vérifier la chaîne avant de signaler un conflit |
| Lignée | appareil déjà couvert = pas de nouveau lien, forçage possible |
| Doutes | toujours validés par l'utilisateur, décisions consignées |
| Relecture | ajout seul, absents signalés |
| Qui fait foi | l'outil pour les relations, le site pour le commercial |
| Lecture | tous les profils Fiche, HTML normalisé, repli texte |
| Masse | lots de 100, résumé par catégorie, détail filtrable, reprise |
| EAN | conservé avec le produit du site, le site fait foi |
| Référence interne | gardée pour chaque produit du site (avec `id_product`), proposée à l'export EveryParts |
| Retour vers le site | gabarits Fiche complète, une ligne par origine, paire |
