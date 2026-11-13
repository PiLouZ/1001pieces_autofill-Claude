# Cahier des charges — Reprise des fiches produit du site 1001pieces.com

**Statut :** En cours — conception validée le 2026-11-10 ; étape 1 (lecteur de description, `src/utils/lecteur_fiche/`), étape 2 (rapprochement, `src/utils/rapprochement_fiche/`), étape 3 (aperçu et enregistrement d'une fiche) et étape 4 (import en masse par lots, `src/utils/reprise_site/`), refonte par questions et étape 5 (export, § 10.10) réalisées le 2026-11-12
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
| À valider | référence trouvée sous une autre marque du groupe, ou seulement par le nom commercial | l'utilisateur choisit |
| Absent | aucun candidat, ni exact ni normalisé | création de l'appareil, validée dans l'aperçu |

- **Pas de création si un candidat normalisé existe.** Un appareil n'est créé que si les deux passes échouent : c'est ce qui empêche les doublons.
- **Les décisions sont mémorisées.** Quand l'utilisateur dit qu'une écriture est « le même appareil » ou « un appareil distinct », la décision est gardée pour la paire d'écritures et n'est plus redemandée. La table `reference_decisions` existante porte sur une **même** référence exacte partagée par plusieurs appareils (2 117 décisions `DISTINCT`) : il faut une mémoire du même genre pour les **paires d'écritures** (§ 9).
- **Doublons existants :** les 467 cas déjà en base ne sont pas corrigés par l'import. Ils apparaissent en « normalisé ambigu » quand une fiche les touche, et leur nettoyage passe par l'outil de doublons existant.
- **Le nom commercial n'est jamais écrasé sans un clic de l'utilisateur** (décision du 2026-11-12, § 10.11). Un nom vide dans l'outil est complété depuis la fiche.
- **Appareil connu, champ différent** (§ 10.11) : même marque et même réf. (ou à la ponctuation près), mais un autre type, une autre écriture de la réf., un autre nom commercial ou une autre marque du groupe sur la fiche. L'appareil est relié ; l'outil est gardé par défaut et l'utilisateur prend la valeur du site d'un clic, cas par cas ou pour tous les cas identiques.
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
| 10 chiffres commençant par `17`, `18`, `28`, `29`, `42` à `49`, `57` à `59`, `61`, ou par `151`, `190`, `191`, `244` à `249`, `270`, `271`, `917` à `919` | Beko |
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

Les débuts Beko ajoutés le 2026-11-13 (`2466300203` était lue Electrolux) sont ceux où la base ne compte que des pièces Beko (129 pièces) ; les débuts mélangés (`140`, `142`, `146`, `192`, `220`, `227`) restent Electrolux.

Cas mélangés, donc des doutes : 10 chiffres commençant par `15`, hors `151` (Electrolux ou Beko), 8 chiffres commençant par `42` (Candy ou Sharp), 8 chiffres commençant par `32` (Sharp ?), 9 chiffres commençant par `16` ou `26` (Beko ?).

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
| nouvelles | état de la reprise `reprise_site_etat` (dernier `id_produit`, date, tailles et chemins de l'export), journal des lots `reprise_site_lots` (durées, taille de la base, mesures), fiches mises de côté `reprise_site_de_cote` — **fait à l'étape 4** |
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
- **Libellé** (décision du 2026-11-12) : le titre de la fiche, sans « (photos non contractuelles) », devient le libellé d'une pièce qui n'en a pas ; un libellé différent est un doute (garder par défaut, ou prendre la fiche). Depuis le § 10.11, le titre est coupé avant « pour <type d'appareil> ».
- **Décisions et plan** (`src/utils/rapprochement_fiche/decisions.py`, sans Qt) : chaque élément appartient à une catégorie du résumé (exacts, normalisés, déjà couverts, à valider, absents, types manquants, remplacements et équivalences, conflits), validée en bloc, laissée de côté (rien n'est écrit, elle revient à la relecture) ou en attente. Un choix individuel l'emporte. Un élément validé sans proposition possible (appareil parmi plusieurs, création sans marque ou sans type) est « à compléter ». Rien ne s'enregistre tant qu'une catégorie est en attente ou qu'une ligne est à compléter. Choisir un appareil d'une autre écriture consigne « même » ; créer malgré une écriture proche consigne « distinct ».
- **Enregistrement** (`EnregistrementFicheService`) par les briques du tronc d'import : `ImportManager._batch_insert_devices` pour les appareils, `import_relations.apply_relations` pour les remplacements (fantômes, obsolescence) et les équivalences (libellé propagé), invalidation des caches comme après un import, puis `EventDrivenSaveService.save_after_import`. Propres à la reprise : pièce fantôme → réelle, liens avec provenance (un lien présent ne fait que compléter sa provenance), origines, produit du site, décisions.
- **Aperçu** : `src/ui/fiche_site_dialog.py`, menu Données → « Lire une fiche du site… » (lien téléchargé hors du thread principal, ou description collée).
- **Vérification** (`tests/unit/test_enregistrement_fiche.py`, sans réseau) : les 3 fiches d'exemple enregistrées puis relues sans rien ajouter, sur l'extrait **et** sur une copie de la vraie base (`scripts/mesurer_migration_fiches.py --fiches`) ; 20744 : la fantôme devient réelle, aucun nouveau lien ; 20746 : 831 provenances complétées, aucun lien créé ; 7285 : pièce créée avec le titre pour libellé, remplacements terme à terme, origines BSH / Indesit et n° de ligne, `481949` écartée puis plus proposée.

---

### 10.4 Import en masse par lots — étape 4 (2026-11-12)

- **Lecture des exports** (`src/utils/reprise_site/exports.py`) : les deux CSV sont lus **ensemble** (jointure par fusion sur `id_produit`, tri contrôlé : un export non trié est refusé). Un produit et ses compatibilités seulement sont en mémoire. `modele_appareil` (« RÉF - NOM ») donne le nom ; `reference_appareil` la référence. La table complète remplace la 1ʳᵉ page de la page publique (`table_site`) ; la marque du produit va en `marque_produit`. L'export complet (13 302 produits, 6 924 928 lignes de compatibilités) se parcourt en **12 s** ; reprendre en fin d'export coûte ≈ 11 s, une fois par session (le lecteur se garde d'un lot à l'autre).
- **Lots** (`lot.py`) : 100 produits ayant un contenu (réglable), dans l'ordre de `id_produit`. Le résumé reprend les catégories de `decisions.py`, plus « profils ambigus » ; une décision vaut pour tout le lot. **Doutes regroupés** par genre et par forme, avec un choix en bloc : référence interne sans rapport avec le code produit (forme où les lettres restent, `ES99999`), EAN différent, libellé différent, référence interne d'une autre pièce, remplacement en conflit, équivalente sans étiquette (étiquette commune ou références écartées). Une fiche ouverte dans l'aperçu (`FicheSiteDialog`, mode « fiche du lot ») garde ses propres décisions.
- **Référence interne différente** : c'est désormais un choix (`CHOIX_IDENTITE`) : enregistrer le produit avec cette référence (proposition) ou non. Elle passe donc par la catégorie « conflits », y compris pour une fiche seule.
- **Écriture** (`RepriseSiteService`) : une connexion en lecture seule gardée toute la session (index des marques en cache ; seules les marques où des appareils ont été créés sont oubliées après un lot). Tous les appareils à créer du lot en **une** insertion du tronc d'import, puis chaque fiche par les briques de l'étape 3 (`EnregistrementFicheService._ecrire` reçoit les appareils déjà créés), puis, dans une seule transaction, le journal du lot, les fiches mises de côté et le dernier `id_produit`. Caches et sauvegarde événementielle une fois par lot. Analyse et écriture dans un thread, avec progression et annulation (entre deux fiches).
- **Choix faits pour que la relance ne change rien** (constatés sur le 1er lot réel) :
  - un appareil absent cité par **plusieurs fiches** du lot (même marque, même forme normalisée) n'est créé qu'une fois ;
  - une ligne à compléter (absente sans type, ou « à valider » sans proposition, par exemple par le seul nom commercial) dont l'appareil est créé par une autre ligne du lot **partage cette création** ;
  - un appareil à choisir parmi plusieurs dont **un seul** candidat est lié par une autre ligne de la même fiche (souvent la table du site, sous la bonne marque) est retenu dès le 1er passage. C'est la règle de mémoire de l'étape 3, appliquée à l'intérieur de la fiche ;
  - une ligne « déjà couverte » dont l'appareil est lié quand même par une autre ligne apporte sa provenance au lien ; deux lignes qui visent le même appareil réunissent leurs provenances.
- **Lecture** : « Réf. fabricant : 10/1863-5010 POUR APPAREILS VN606E » ne garde que la référence de tête ; la suite est un bloc non lu (sinon `POUR` et `APPAREILS` devenaient des équivalences).

**Mesure du 1er lot** (`scripts/mesurer_lot_reprise.py`, copie de la vraie base par l'API backup, export complet, produits 7084 à 7191). Tout est validé en bloc, avec les propositions des groupes de doutes et les lignes à compléter laissées de côté : c'est la **borne haute** de la croissance.

| | 1ᵉʳ lot |
|---|---|
| Fiches | 100 (83 pièces absentes de l'outil, 17 réelles), 22 sans aucun doute |
| Lignes d'appareils | 50 929 (description 22 668, table 640, les deux 27 621) |
| Niveaux | exact 45 410 (89,2 %), à valider 3 864 (7,6 %), absent 1 650 (3,2 %), exact multiple 5 |
| **Déjà en base** | **47,0 %** (déjà liées 17 212, déjà couvertes 6 715) ; nouveaux liens 26 181 |
| Doutes les plus fréquents (fiches) | réf. interne différente 31, lecture 31, à valider 28, libellé différent 17, marque à choisir 11, origine inconnue 8 |
| Doutes regroupés | 17 groupes (dont 4 de réf. internes par forme), 3 profils ambigus |
| Lignes à compléter laissées de côté | 374 |
| Écrit | 1 329 appareils (1 382 lignes de création), 231 pièces, 25 230 liens (17 188 provenances complétées), 87 remplacements, 194 membres d'équivalence, 100 produits du site |
| Durées | analyse **6,7 s**, écriture **0,5 s** |
| **Croissance de la base** | **+9,9 Mo** (999,9 Mo au départ) |
| Relance du même lot | **0** appareil, lien, provenance, relation ou produit ajouté |

Sur 3 lots consécutifs (300 fiches), la base grandit de 26 Mo (9,9 + 11,1 + 5,1) et chaque lot prend moins de 10 s. Si ce rythme se maintient, les 133 lots ajouteraient de l'ordre de **1,1 à 1,3 Go** (en tout validé), pour une vingtaine de minutes de calcul ; c'est la validation des doutes qui fixera la durée réelle. Relancer le lot 1 **après** les lots 2 et 3 ajoute 11 liens et aucun doublon : ce sont des appareils créés par les lots suivants, que des lignes laissées de côté du lot 1 retrouvent maintenant.

Vérification (`tests/unit/test_reprise_site.py`, sans réseau) : jointure des exports, tri contrôlé, lots et dernier `id_produit` ; lot sur une base construite (création partagée entre 2 fiches, groupe `ES99999` ignoré en bloc) ; interruption au milieu de l'écriture puis reprise, même résultat qu'un passage sans interruption ; relance sans aucun ajout ; fermer et reprendre au lot suivant ; export différent (repartir de zéro ou continuer) ; fiches mises de côté puis reprises ; profils ambigus laissés de côté ; lot des 3 fiches d'exemple sur l'extrait de la base ; fenêtre rendue hors écran.

### 10.5 Rien de faux en bloc — refonte, étape 1 (2026-11-12)

Une équipe d'agents (données et UX) a rejoué « Tout valider » sur le 1ᵉʳ lot réel. Le plan de refonte de la reprise (écrans par questions, règles mémorisées) est en 5 étapes. L'étape 1 corrige d'abord ce qui s'écrivait de faux :
- **Type** : le type commun d'une catégorie ne remplace jamais un type déjà trouvé (table, ligne, base, catégorie du produit). Il n'est plus proposé que pour les « types manquants ». Avant, il aurait pu faire créer les 1 100 filtres de hotte de la fiche 7188 en lave-linge.
- **Candidat unique** : il n'est relié en bloc que s'il a la même référence à la ponctuation près. Trouvé par le seul nom commercial, c'est un autre appareil : la ligne est à compléter. Cela retire 42 liens faux. Même règle pour le candidat repris d'une autre ligne de la fiche.
- **Nom commercial** : parmi plusieurs candidats, celui de même référence est proposé.
- **Recherche dans le groupe** : une ligne avec un en-tête de marque n'a été cherchée que sous cette marque. Les autres marques annoncées sont donc cherchées comme marques du groupe. Cela évite 28 doublons, par exemple Ignis `854020013030`, qui existe sous Whirlpool.
- **Référence interne** égale au code produit à la ponctuation près (`10-2930-5010` / `10/2930-5010`) : « égale ».
- **Équivalente sans chiffre** (`Brandt`, `:`, erreurs de lecture) : jamais écrite en bloc.
- **Référence illisible** : sans chiffre, avec parenthèses ou `:`, plusieurs codes sur une ligne, ou commençant par une marque (`C :`, `VF3017 (VF 3017)`, `FCSM6 BL2M6100 855620004000`, `ARDO CL60B`). Elle n'est jamais créée en bloc : la ligne est à compléter.

**1ᵉʳ lot remesuré** (même protocole qu'au § 10.4) :

| | Avant | Après |
|---|---|---|
| Appareils créés | 1 329 | 1 287 |
| Liens créés | 25 230 | 25 271 |
| Lignes à compléter laissées de côté | 374 | 360 |
| Appareils créés illisibles | 23 | **0** |
| Lignes « à valider » reliées à une autre référence | 42 | **0** |
| Doublon Ignis / Whirlpool `854020013030` | créé | **évité** |
| Durées / croissance | 6,7 s + 0,5 s / +9,9 Mo | 5,6 s + 0,4 s / +9,9 Mo |
| Relance du même lot | 0 ajout | **0 ajout** |

Les liens augmentent un peu malgré les 42 liens faux retirés, parce que des appareils sont maintenant retrouvés sous une autre marque du groupe au lieu d'être créés en double.

Vérification : `tests/unit/test_reprise_rien_de_faux.py` (un test par correctif).

### 10.6 Moteur de questions — refonte, étape 2 (2026-11-12)

Décisions de l'utilisateur (2026-11-12) :
- **règles mémorisées** : posées au 1ᵉʳ lot, appliquées ensuite avec un rappel, révocables ;
- **fiche incomplète** : écrite pour le reste, puis signalée « à revoir » ;
- **lecteur** : corrigé dans une étape à part, après les écrans ;
- **nom de la fenêtre** : « Importer les fiches du site ».

`src/utils/reprise_site/questions.py` (sans Qt) remplace, pour un lot, les catégories validées en bloc :
- **un récapitulatif sans décision** : compatibilités déjà connues, déjà couvertes, nouvelles, remplacements, équivalentes d'origine reconnue ;
- **des questions**, chacune avec ses cas, des exemples et une réponse proposée.

Rien de douteux ne s'écrit sans la réponse à sa question. Tant qu'une question est sans réponse, le lot ne s'enregistre pas. « Accepter les propositions » ne répond jamais à une question sans proposition.

| Clé | Question | Proposé |
|---|---|---|
| R1 | même réf. sous une autre marque du groupe = même appareil ? | oui |
| ~~R2~~ | ~~appareil classé sous un autre type sur le site : le relier (type de l'outil gardé) ?~~ Retirée le 2026-11-12 : l'appareil est relié, son type devient un écart (§ 10.11) | — |
| R3 | même nom commercial, réf. différente : nouvel appareil ? | créer |
| R4:A\|B | même réf. sous une marque hors du groupe : B est-il du groupe de A ? | — |
| R5 | réf. produit sans rapport avec le code produit : la garder ? | garder |
| R6 | titre ≠ nom de la pièce : quel nom ? | garder l'outil |
| R7 | pas de code produit : reprendre la pièce sous la réf. produit ? | — |
| Q1 | créer les appareils inconnus (marque et type connus) ? | créer |
| Q2:fiche | type des appareils à créer | d'après la base (même marque, même début de réf.) |
| Q3:fiche | marque des appareils à créer | marque annoncée qui a le plus de réf. de même début |
| Q4:forme | équivalentes sans marque d'origine | « écarter » sans chiffre ; la marque annoncée si elle est seule |
| Q5, Q6, Q7 | remplacement en conflit, EAN différent, réf. produit d'une autre pièce | garder, site, prendre |

**Comment les règles et les réponses sont traitées :**
- Les règles R1 à R7 sont mémorisées dans `regles_reprise` (`data/reprise_fiches.json`, propre au poste, hors git) et révocables.
- Un « oui » à R4 ajoute la marque au groupe (`groupes_marques`), puis le lot est relu (`RepriseSiteService.relire_lot`), en gardant les réponses déjà données.
- Les réponses deviennent des choix individuels (`DecisionsFiche`). Le planificateur de l'étape 3 reste seul à décider de ce qui s'écrit.
- Une ligne sans question est laissée de côté et sa fiche est signalée « à revoir » : appareil à choisir parmi plusieurs sans candidat de même réf., réf. illisible, ou ligne encore à compléter après réponse.
- Le rapprochement note maintenant **pourquoi** une ligne demande un avis : `AppareilRapproche.motif` (cf. `MOTIFS`), et `hors_groupe` pour la même réf. sous une marque hors du groupe.

**1ᵉʳ lot réel** (`scripts/mesurer_lot_reprise.py --questions --regles <fichier de test>`, copie de la base) :
- **32 questions** au lieu de 4 104 lignes « à valider » : 12 règles (7 genres, dont 6 groupes de marques R4) et 20 questions du lot (1 « créer », 1 type, 6 marques, 11 équivalentes, 1 conflit) ;
- **14 ont une proposition** et se règlent d'un clic : R1 (788 lignes), R2 (3 024), R3 (42), Q1 (1 230 créations), Q2 (« Machine à café » pour les 17 Philips de la fiche 7136, d'après la base)… ;
- les questions sans proposition sont les vraies : Elica dans le groupe Whirlpool ? Bluesky, Far, Altus, Ardem dans le groupe Beko ? fiches sans code produit, marque de 6 fiches, 7 équivalentes inconnues ;
- avec les réponses simulées (groupes : oui), 1 251 appareils et 26 071 liens sont créés ; 14 fiches sont « à revoir » (301 lignes laissées de côté) ;
- la **relance n'ajoute rien** ;
- **lot 2** (produits 7192 à 7292) : 11 questions seulement, dont 5 règles déjà mémorisées.

Les écrans (étape 3 des fiches « à revoir » persistantes, étape 4 des écrans par questions) viennent ensuite ; d'ici là, la fenêtre garde l'affichage par catégories.

Vérification : `tests/unit/test_reprise_questions.py` (base et exports construits : une question par genre, rien sans réponse, propositions partielles, réponses écrites et relance sans ajout, règles mémorisées puis révoquées dans un fichier de test, R4 « oui » puis relecture).

### 10.7 Fiches « à revoir » — refonte, étape 3 (2026-11-12)

Une fiche enregistrée dont des lignes ont été laissées de côté **par le lot**, et non par l'utilisateur, est inscrite dans `reprise_site_de_cote` avec la raison « partielle : N appareil(s) à revoir ». Ces lignes sont :
- les appareils à choisir parmi plusieurs ;
- les références illisibles ;
- les lignes encore à compléter après réponse ;
- celles laissées par « Laisser de côté les lignes à compléter ».

Elle n'en est retirée qu'une fois complète. Relue (« Reprendre les fiches de côté »), elle ne pose plus que ses lignes restantes, et ce qui est déjà écrit ressort « déjà lié » : aucun doublon. Aucune migration n'a été nécessaire, la colonne `raison` existant déjà.

Vérification : `test_reprise_questions.py::test_fiche_partielle_a_revoir_puis_complete`.

### 10.8 Écrans par questions — refonte, étape 4 (2026-11-12)

- **Panneau commun** (`src/ui/questions_reprise.py`) aux deux fenêtres :
  - « Ce que l'outil fera sans vous » : un récapitulatif, sans aucun clic ;
  - « Règles à poser une fois » (mémorisées) ;
  - « Questions » ;
  - « Règles déjà posées » (« Revenir sur cette règle »).

  Une carte par question donne le nombre de cas, des exemples et la réponse proposée (bouton vert). Elle se replie une fois répondue ; « Modifier » la rouvre. « Voir les lignes » mène aux lignes concernées.
- **« Importer les fiches du site »** (nouveau nom de la fenêtre de reprise, menu Données) a trois onglets :
  - « À décider » ;
  - « Fiches du lot » : ce qu'il reste pour chaque fiche, filtrable ;
  - « Toutes les lignes » : la vue virtuelle, en vocabulaire métier, avec un filtre par question.

  « Accepter les propositions… » montre d'abord ce qu'il va faire. Répondre « oui » à une règle de groupe de marques relit le lot automatiquement. « Fiches à revoir (N) » remplace « Reprendre les fiches de côté ». Les tableaux « Catégorie / Éléments / Décision / Type commun » et l'onglet « Doutes regroupés » disparaissent.
- **« Lire une fiche du site »** applique le même moteur à un lot d'une seule fiche :
  - la carte de la pièce est en langage métier ;
  - les onglets sont « Appareils », « Anciennes références et équivalentes » (conflits marqués) et « À savoir » ; l'onglet « Pièce » disparaît, ses doutes deviennent des questions ;
  - la marque et le type ne s'affichent qu'avec « Créer l'appareil ».

  Les choix ligne par ligne (`QuestionnaireLot.individuels`) l'emportent sur les réponses et sortent leurs lignes des questions. En mode « fiche du lot », « Garder ces choix pour le lot » les rend au lot.
- **Vocabulaire :**
  - lien → compatibilité ;
  - en base → dans l'outil ;
  - fantôme → ancienne référence ;
  - étiquette d'origine → marque d'origine ;
  - « → » → « remplacée par » ;
  - id_product → n° du produit sur le site.

Vérification :
- rendu hors écran du 1ᵉʳ lot réel (à décider, après propositions, fiches, lignes) et des deux modes de « Lire une fiche du site » ;
- tests d'écran réécrits (`test_reprise_site.py::test_fenetre_reprise_rendue_et_fiche_du_lot`, `test_enregistrement_fiche.py::test_apercu_rendu_et_enregistrement`), qui vérifient aussi que le `data/reprise_fiches.json` du poste n'est jamais écrit par les tests.

### 10.9 Correctifs du lecteur — refonte, étape 5 (2026-11-12)

Ce sont les erreurs de lecture relevées sur le 1ᵉʳ lot réel (audit des données). Elles devenaient des questions ou des données fausses.

| Fiche | Écrit sur le site | Lu désormais |
|---|---|---|
| 7089, 7095-7097 | `Bauknecht Réf. fabricant : 10/1863-5010 POUR APPAREILS VN606E` | réf. de la pièce `10/1863-5010` + appareil Bauknecht `VN606E` |
| 7188 | `Références équivalentes Rosières : 49025106 …` | marque d'origine Rosières (plus d'équivalentes `Rosières`, `Electrolux`, `Brandt`, `:`) |
| 7188 | `Remplace les dimensions : C00280008 …` (faute du site) | anciennes références |
| 7095… | `C : - cm` (cote) | texte libre, pas un appareil |
| 7091 | `VF3017 (VF 3017)` | réf. `VF3017`, nom `VF 3017` |
| 7138 | `HR 6325 - HR632501` (famille - modèle) | réf. `HR632501`, si elle prolonge la famille ; `HR 6328 - HR6374` reste tel quel |
| 7182 | `852576929010 AKZM769/WH Four à Pyrolyse`, ou `Four à Pyrolyse` seul après un appareil | type « Four » (début connu), plus une marque inconnue |
| 7091, 7179 | `Référence Brauknecht : …`, `Référence Ego : …` | références par marque (marque à une faute près d'une marque annoncée ou connue ; fabricant écrit avec une majuscule, suivi de références) |

**Côté rapprochement :**
- **Alias par défaut** : `GE` → General Electric et `Brauknecht` → Bauknecht.
- **Une seule marque annoncée après alias** : c'est la marque de la ligne sans en-tête. Cela règle la fiche 7112.
- **Nom commercial d'un appareil déjà cité** : une ligne sans marque, absente, dont la « référence » est le nom commercial (sur la fiche, ou dans l'outil) d'un appareil déjà cité par une autre ligne est un doublon, et rien n'est créé. Exemple : fiche 7164, 208 lignes sur 209 (`WAT4564W` = Bauknecht `858341142074`).

**Mesures :**
- **Export complet** (`scripts/mesurer_lecteur_fiches.py`) : **10 878 fiches lues sans doute (89,0 %)**, contre 10 867 (88,9 %) au § 10.1 : 11 de plus, aucune de moins ; 6 454 931 lignes d'appareils.
- **1ᵉʳ lot réel** (mode questions, copie de la base) :
  - 26 questions au lieu de 32 ;
  - **84 lignes « à revoir » au lieu de 301**, dans 12 fiches au lieu de 14 ;
  - 91 remplacements au lieu de 87 ;
  - relance sans ajout.

Vérification : `test_lecteur_fiche.py::TestCorrectifsDuLot1` et `test_reprise_rien_de_faux.py` (alias GE, doublons par le nom).

### 10.10 Export — étape 5 (2026-11-12)

**Fiche complète** (§ 8.1) :
- La 2ᵉ réf. du code produit est désormais **mémorisée avec le n° de ligne 0** (`piece_equivalence_groups.ligne_fiche`). Avant, `0` devenait vide à l'enregistrement et la paire ne se retrouvait plus. Une fiche déjà reprise le récupère à sa relecture (`COALESCE`).
- `FicheProduitService.references_fiche` part des lignées actuelles (`references_liees`, inchangée) et rend :
  - le **code produit** : la pièce, puis ses équivalentes de ligne 0 si la pièce a un produit du site (et qu'elles n'en ont pas elles-mêmes) ;
  - « **Remplace** » : les anciennes références des deux ;
  - **une ligne d'équivalentes par marque d'origine**, puis par ligne mémorisée (`lignes_par_origine`), rangées par n° de ligne de la fiche ; chaque équivalente garde ses anciennes références ;
  - sans les **références écartées** (`decisions_references`).
- Sans rien de mémorisé (pièce de l'outil, 754 réf. existantes, base non migrée) : une seule ligne d'équivalentes et la seule référence, comme avant.
- `FicheProduitGenerator` : `{reference}` reçoit la paire jointe par le séparateur ; une ligne `equivalentes_template` par liste. Les profils enregistrés n'ont pas à changer, et le lecteur accepte déjà `{reference}` comme `{references}`. L'onglet Fiche montre deux lignes d'équivalentes dans son aperçu.
- Limite connue : la 2ᵉ réf. du code produit recherchée seule (`C00319033`) n'a pas de produit. Sa fiche est celle d'avant : pas de paire, et la pièce principale y figure en équivalente.

**Export EveryParts** (§ 8.2) :
- Le terme recherché passe par `resolve_current_ref`, puis par `produits_site_de` (`00703010` → `11051894` → `GAU11051894`).
- **Un produit** : sa référence interne est pré-remplie, modifiable, avec le n° du produit dans le message.
- **Plusieurs produits** : une liste « Produit du site » dans le même dialogue remplit le champ et le nom du fichier.
- **Aucun produit**, export HTML ou recherche multiple : comportement actuel.
- Le produit retenu alimente `{ref_interne}` et `{id_product}` (colonnes et nom de fichier). Il est gardé même si la référence est retapée. L'export rapide ne prend que les variables, et seulement si la pièce n'a qu'un produit.
- Format par défaut inchangé.

**Vérification** (`tests/unit/test_fiche_export_site.py`, extrait de la vraie base, sans réseau ni réglage du poste) :
- les 3 fiches d'exemple enregistrées, régénérées puis relues : même nombre de lignes d'appareils (1 840, 831, 450), plan vide, aucun lien créé ni complété, base identique ;
- 7285 : code produit `481073071153 C00319033`, une ligne BSH `00145522`, `481949` absente (même rajoutée à la main au groupe) ;
- EveryParts : 20746 → `EL1113161010`, `00703010` → `GAU11051894`, pas de produit → terme recherché ;
- deux produits : vrai dialogue rendu hors écran, choix → champ et nom du fichier ;
- aperçu d'export de 7285 rendu hors écran ;
- suite complète (1 991 tests), `compileall`, lancement de `run.py`.

### 10.11 Trois correctifs avant la refonte de l'ergonomie (2026-11-13)

**1. Libellé coupé au type d'appareil** (`src/utils/rapprochement_fiche/coupe_titre.py`, `libelle_depuis_titre`) :
- Le libellé garde ce qui précède « pour <type> ». Les types reconnus sont ceux de l'onglet Appareils et toutes leurs appellations (actives ou non), au singulier ou au pluriel, avec un tiret ou une espace, sans accents ni casse : « machine à laver » = lave-linge, « refrigerateur » est reconnu.
- Les types bruts de la base (« Porte », « Filtre », « Accessoires ») ne servent pas : « Joint pour porte de four » reste entier.
- Ce qui suit le type est retiré (« (pièce générique) », « et cuisinière », « (lot de 2) »). Une caractéristique chiffrée hors parenthèses est gardée à la suite (choix B de l'utilisateur) : « Résistance pour sèche linge 1900W » → « Résistance 1900W ».
- Même règle pour la fiche seule et pour le lot (le rapprochement est commun). Les appellations viennent de la configuration des exports (`ConfigurationRapprochement.appellations_appareils`, renseignée par `EnregistrementFicheService`).
- Un libellé écrit en entier par une reprise antérieure (statut `ancienne_regle`) est remplacé sans question.
- **Mesure sur l'export complet** (13 296 titres) : **8 960 coupés (67,4 %)**. 757 titres ont « pour » suivi d'autre chose (« pour porte de four », « pour panier de lave-vaisselle », fautes « sèche-ligne », « lave-vaisseille ») et restent entiers. 132 titres gardent leur fin chiffrée (« Thermostat A13-0135-A266 », « Spot halogène 20W G4 12V »).
- **Coupes douteuses relevées** :
  - « Vis de fixation pour plaque métallique HPF120 sur hotte » donne « Vis de fixation métallique HPF120 sur hotte » (« plaque » pris pour le type) ;
  - « FILTRE À GRAISSE pour hotte ariston 275x217 mm » donne « FILTRE À GRAISSE ariston 275x217 mm » (la marque reste) ;
  - « machine à expresso » n'est pas reconnu (l'appellation est « machine expresso ») ;
  - 1 037 libellés n'ont plus qu'un mot (« Pressostat ») : voulu, le Titre ajoute le type.

**2. Appareil connu, champ différent** (fiche et lot, même moteur) :
- **Rapprochement** : `AppareilRapproche.ecarts`, une liste d'`Ecart(champ, outil, site, appareil_id)` sur l'appareil désigné par la ligne (retenu, proposé, ou seul candidat de même réf. sous une marque du groupe). Les champs comparés :
  - le type (table du site ou ligne) ;
  - la marque, seulement dans un même groupe et seulement si elle vient d'un en-tête ou de la table ;
  - l'écriture de la réf. (à la ponctuation près) ;
  - le nom commercial.
- **Bruit écarté sur les noms** : pas d'écart à un ou deux caractères de fin près (indice de version : « AZB 82001 » / « AZB8200 »), ni quand le nom lu contient un code de 9 chiffres ou plus (liste d'appareils lue comme un nom, fiches 7146 et 7169).
- **R2 disparaît.** Un appareil classé sous un autre type est relié (niveau exact ou normalisé, sans doute) avec le type de l'outil ; le type du site devient un écart. Une règle R2 déjà mémorisée est ignorée.
- **Choix** : `DecisionsFiche.champs[(ligne, champ)]` vaut `outil` ou `site`. Sans choix, l'outil est gardé, rien n'est écrit, et l'écart revient à la relecture. Un champ vide dans l'outil (nom commercial) prend la fiche sans question.
- **Lot** : `QuestionnaireLot.ecarts`, des `GroupeEcart` par cas identiques : clé `E:type:<outil>→<site>`, `E:marque:…`, `E:ref`, `E:nom`.
  - Une réponse vaut pour tout le groupe ; un choix par ligne (`E:…@fiche:ligne`, ou fait dans l'aperçu de la fiche) l'emporte.
  - Un écart ne bloque jamais le lot, et « Accepter les propositions » n'y répond pas.
- **Écriture** :
  - « prendre le site » donne `plan.maj_appareils` (id → colonnes). L'écriture se fait après le lot, sur le thread principal, par `EventDrivenSaveService.enregistrer_champs_appareils` (`save_cells_batch`). Sans fenêtre (scripts, tests), c'est la même `update_multiple_cells_batch` ;
  - « garder l'outil » est mémorisé dans la table `decisions_champs(appareil_id, champ, valeur_site)`. La relecture ne repropose plus cette valeur du site ; une autre valeur est reproposée.
- **Écran** (`questions_reprise.py`, panneau commun) : une section « Appareils connus, valeur différente sur le site » et une carte par groupe.
  - Chaque cas s'affiche sur deux lignes, Outil puis Site. La valeur qui diffère est un bouton ambre ; celle gardée est verte (trait fin quand elle est gardée par défaut) ; l'autre est barrée.
  - En bas de carte : « Garder l'outil (N) » (proposé) et « Prendre le site (N) ». Au-delà de 4 cas, un bouton « Voir les N cas » affiche la suite.
  - Dans la fiche seule, les clics deviennent des choix ligne par ligne, rendus au lot par « Garder ces choix pour le lot ».
- **1ᵉʳ lot réel** (copie de la base, réponses simulées comme au § 10.6) :
  - 25 questions (26 avant : R2 retirée), 84 lignes à revoir comme avant, relance sans ajout ;
  - écarts : 6 groupes de type (`Four vapeur → Four` 2 796 cas, `Sèche-linge → Lave-linge` 192, `Four → Four vapeur` 28, `Cuisinière → Four` 13…), 12 groupes de marque (Bauknecht ↔ Whirlpool, Ignis, Laden, Hotpoint-Ariston… ; `Elica → Ikea` vient de la réponse simulée « oui » au groupe), 19 écritures de réf., et 159 noms (749 avant le filtre du bruit) ;
  - aucun nom vide à compléter dans ce lot.

**3. Ordre de « Remplace les références »** :
- Nouvelle colonne nullable `piece_supersessions.rang_fiche` : la position de l'ancienne référence dans la ligne de la fiche. Elle est écrite à la reprise, et complétée à la relecture pour un remplacement déjà présent (`plan.rangs_remplace`, qui ne compte pas dans `vide`).
- `FicheProduitService.references_fiche` range les références mémorisées dans cet ordre, puis les autres dans l'ordre actuel. Une pièce sans mémoire ne change pas.
- 481073071153 donne `C00535957 488000535957 C00309416 482000032568`.
- La règle déduite (paires terme à terme) a été écartée : elle donnait `488000535957 C00535957 482000032568 C00309416`. L'ordre à l'intérieur d'une paire varie selon la ligne de la fiche (Indesit d'abord ici, Whirlpool d'abord dans le code produit).
- 1ᵉʳ lot réel : 102 positions mémorisées.

**Vérification** :
- Tests : `test_coupe_titre.py`, `test_ecarts_fiche.py`, `test_ecarts_ecrans.py` (les deux fenêtres rendues hors écran, images dans `AUTOFILL_RENDUS`), `test_reprise_questions.py::test_ecarts_en_bloc_dans_le_lot_puis_relance_sans_ajout` et `test_fiche_export_site.py` (ordre, relecture qui complète la position).
- Les 3 fiches d'exemple, sur l'extrait et sur une copie de la vraie base : relues sans rien ajouter.
- Suite complète (2 029 tests), `compileall`, lancement de `run.py`.

**Suite notée par l'utilisateur (2026-11-12)** : pour une référence Whirlpool, Indesit ou Beko, demander la référence associée (de l'un des deux autres groupes, ou aucune). C'est une mémoire de paires utile au code produit, à l'appariement des remplacements et aux imports PDF / CSV. Elle ne suffit pas à l'ordre exact du point 3 : l'ordre à l'intérieur d'une paire varie d'une ligne à l'autre. À traiter avec la refonte de l'ergonomie, ou dans une étape à part.

### 10.12 La reprise devient un import comme les autres — audit, mesure, plan (2026-11-13)

**Décision de l'utilisateur (2026-11-13)**, pour les deux fenêtres : une fiche du site est une source de plus, comme un PDF ou un CSV. Une fiche seule suit l'import d'un fichier ; un lot suit l'import de plusieurs fichiers (cartes), en gardant le propre du massif (deux exports, avancement, relance sans doublon). Un doute sur un appareil n'est pas un doute sur la relation avec la pièce. Des écrans simples.

**Chemin d'import actuel** (`src/core/import_manager.py`, `src/ui/fenetre_import.py`) :
1. Fichier choisi, glissé ou collé → `ImportConfiguration` ; réf. de pièce = nom du fichier (champ saisi pour un collage).
2. `ImportDialog` (non bloquant) : aperçu de 5 lignes, correspondance des colonnes (`ref_modele`, `commercial_ref`, `type`, `manufacturer`, `other_ref`, `notes`), libellé, Obsolète. Fichier seul : section « Succession » (remplace, remplacée par, équivalente à). Plusieurs fichiers : une carte par fichier (réf., libellé, Obsolète, « Remplacée par »), réf. commune, zone de groupes (lignées, équivalences).
3. Aperçu à blanc facultatif (`ImportPreviewDialog`) : comptages et « Orthographe alignée sur la base ».
4. Import (QThread) : casse des marques et types alignée (`CasseNormalisationService`), auto-complétion Type/Marque par réf. exacte (`proposer_type_fabricant`), appareil cherché par la clé `lower(ref_modele)|lower(commercial_ref)` **sans la marque**, créations en lot, champs vides des appareils existants complétés (jamais écrasés), liens par `add_or_update_piece_with_description`, puis relations (`apply_relations` ou `_apply_succession_from_config`).
5. Après : aucune fenêtre n'est imposée. Récapitulatif dans l'historique ; boutons « Suggestions à valider (N) » (`SuggestionValidationDialog` : paire Type/Marque proposée par similarité de réf.) et « Auto-complétés à vérifier (N) » (`AutocompletionReviewDialog`). Refus dans `refus_completions`.
6. L'import PDF ne pose **aucune** question par appareil (type, marque, écriture) : les seules fenêtres sur les appareils sont ces deux fenêtres d'après l'import.

**Mesure sur le 1ᵉʳ lot réel** (produits 7084 à 7191, copies de la base par l'API backup, sans réseau). Les mêmes lignes lues (lecteur et marque retenue par la reprise) passent d'un côté par la reprise (mode questions, réponses simulées comme au § 10.6), de l'autre par `ImportManager._run_import_files`, une carte par fiche (73 fiches ont des appareils) :

| | Import d'origine (réf. + nom) | Reprise (marque + réf., 2 passes) |
|---|---|---|
| Appareils créés | 4 402 | 1 262 |
| dont même marque et même réf. qu'un appareil existant | **2 829** (le nom commercial diffère ou manque : 2 301 créés sans nom) | 0 |
| dont doublons de ponctuation | 0 | 0 |
| dont même réf. sous une autre marque (Beko / Altus, Far ; Whirlpool / Ignis, Laden) | 36 | 0 |
| créés en double entre fiches | 25 | 0 |
| créés sans type / sans marque | 17 / 28 | 0 / 0 |
| Lignes rattachées à un appareil d'une autre marque | 272 (presque toutes du même groupe : Bauknecht / Whirlpool, Candy / Hoover), sans trace | relié (R1) ou question |
| Liens créés | 31 930 (les lignes « déjà couvertes » par la lignée sont liées) | 25 343 |
| Auto-complétés à vérifier | 3 107 appareils | — |
| Suggestions à valider | 21 appareils | — (26 questions) |
| Existants complétés ou modifiés | 0 | 0 |
| Relance du même lot | 0 appareil, **+418 liens** | 0 ajout |

- Ce qu'on perd avec la clé de l'import : 2 829 doublons sur un lot (≈ 370 000 sur la reprise entière), dus au nom commercial dans la clé ; les liens de lignée en double ; 418 liens perdus au 1ᵉʳ passage (un appareil créé par une carte et cité par une carte suivante n'y est pas rattaché, `_rattacher_doublon_batch` : défaut du chemin à plusieurs fichiers, hors reprise).
- Ce qu'on gagne : l'auto-complétion et les suggestions de l'import, aucune question.
- La ponctuation ne pèse rien sur ce lot (aucun niveau « normalisé ») ; elle compte sur la base entière (467 collisions, § 5.2).
- **Conclusion** : la fiche garde son identification (marque + réf., deux passes, lignée), qui résout chaque ligne en appareil connu ou à créer ; tout le reste suit l'import.

**Ce qui se branche tel quel sur l'import** : écran `ImportDialog` (aperçu, carte, libellé, Obsolète, « Succession » ou cartes), casse alignée, auto-complétion du type et de la marque des appareils à créer, complétion des champs vides des existants, écriture des appareils (`_batch_insert_devices`) et des relations (`apply_relations`), garde des conflits de remplacement, historique, suggestions à valider, auto-complétés à vérifier, `EventDrivenSaveService.save_after_import`.

**Ce qui reste propre à la reprise, sans écran** : lecteur (`lecteur_fiche`), deux exports CSV et lots, avancement et relance (`reprise_site_etat`, `_lots`), identification marque + réf. et lignée (« déjà couvert » = pas de lien), coupe du libellé, provenance des liens, `produits_site` / EAN / réf. interne (le site fait foi, écrits sans question), marques d'origine et n° de ligne des équivalentes, ordre des « Remplace » (`rang_fiche`), pièce fantôme devenue réelle.

**Ce qui disparaît** : moteur de questions R1 à R7 et Q1 à Q7 (`reprise_site/questions.py`, `regles_reprise`), catégories validées en bloc et groupes de doutes (`decisions.py` réduit au plan d'écriture), écarts outil / site (`Ecart`, `GroupeEcart`, `decisions_champs` n'est plus écrite), fiches « à revoir », panneau `questions_reprise.py`, onglets et vue virtuelle de `reprise_site_dialog.py`, `fiche_site_dialog.py`.

**Règles qui remplacent les questions** (celles de l'import) :

| Avant | Après |
|---|---|
| R1 même réf. sous une marque du groupe | relié (l'import le fait déjà, sans trace) |
| R3 même nom, autre réf. ; Q1 créer les inconnus | créé |
| R4 marque hors du groupe | créé sous la marque de la fiche |
| Q2 type d'un appareil à créer | auto-complétion, sinon vide → « Suggestions à valider » |
| Q3 marque d'un appareil à créer | ligne non importée, comptée (§ 10.13) |
| R5, Q6, Q7 réf. interne, EAN | le site fait foi, écrit, noté dans l'historique |
| R6 libellé | champ libellé de la carte : celui de l'outil, ou le titre coupé s'il est vide |
| R7 sans code produit | carte à réf. vide, à saisir ou à décocher |
| Q4 équivalentes sans origine | origine vide ; une erreur (`481949`) se retire de la « Succession » |
| Q5 remplacement en conflit | garde de l'import (fenêtre existante) |
| appareil parmi plusieurs sans proposition, réf. illisible | ligne non importée, comptée dans l'historique |
| écarts outil / site | règle de l'import : un champ vide est complété, jamais écrasé |

**Réf. associée Whirlpool / Indesit / Beko** : la question a sa place dans la « Succession » de l'import (fichier seul) et sur la carte (plusieurs fichiers), pour **tous** les imports, quand la réf. de la pièce a la forme d'un de ces trois groupes (table des formats, § 5.5). Une fiche du site la remplit d'office avec la 2ᵉ réf. de son code produit. Mémoire : équivalence de n° de ligne 0 (déjà en place, § 10.10) ; la réponse « aucune » dans `decisions_references` (décision `sans_associee`), pour ne plus la poser.

**Plan proposé** (en attente de l'accord de l'utilisateur) :
1. Moteur : une fiche → des lignes d'import déjà résolues + relations des cartes ; écriture par l'import, puis le propre de la reprise. Règles du tableau ci-dessus. Anciennes fenêtres inchangées.
2. « Lire une fiche du site » ouvre `ImportDialog` en fichier seul. Un lien de 1001pieces.com collé dans le tableau (Cmd+V) ouvre le même import d'une fiche (demande du 2026-11-13).
3. « Importer les fiches du site » ouvre `ImportDialog` en cartes (une par fiche), avec la barre d'avancement du massif.
4. Réf. associée Whirlpool / Indesit / Beko, pour tous les imports.
5. Retrait du moteur de questions, des écarts et des anciennes fenêtres.

### 10.13 Moteur : une fiche est écrite par l'import — refonte, PR 1 (2026-11-13)

**`ImportManager`** (ajouts génériques, sans effet sur les imports PDF, CSV et collage) :
- `FileType.FICHE_SITE` : des lignes déjà lues, un dict par ligne. Une ligne porte soit l'id d'un appareil reconnu (`CLE_APPAREIL`), soit un appareil à créer avec sa clé d'identité (`CLE_IDENTITE` = marque + forme normalisée, la règle du § 5.2, à la place de « réf. modèle | nom commercial »). Elles passent par le chemin batch : orthographe alignée, auto-complétion, appareils créés, liens, suggestions.
- Un appareil reconnu garde ses champs ; la ligne ne complète qu'un type ou une marque vides.
- `ImportConfiguration.apres_ecriture(import_manager, results)` : un crochet appelé après les appareils, les liens et les relations, dans le thread de l'import. Il n'est jamais appelé en simulation.
- **Correctif de l'import de plusieurs fichiers** : un appareil créé par un fichier entre dans le cache partagé (`_retenir_appareils_crees`). Un fichier suivant qui le cite y est relié dès le 1ᵉʳ passage. Sur le 1ᵉʳ lot réel, c'étaient 418 liens posés seulement par une relance (§ 10.12).

**Écriture d'une fiche** (`EnregistrementFicheService.ecrire_par_import`) :
1. la pièce (fantôme → réelle, libellé), avant l'import, pour que les relations propagent le libellé ;
2. un fichier `FICHE_SITE` par fiche (lignes : `lignes_import(plan)`), puis `_run_import_files` ;
3. dans le crochet, fiche par fiche : provenance des liens, remplacements et équivalences, origines, ordre des « Remplace », produit du site, décisions.

Un lot est un import de plusieurs fichiers (`RepriseSiteService._ecrire_lot`). Une fiche que l'import n'a pas traitée (annulation) n'a rien de propre écrit, et l'état du lot n'avance pas. Les anciennes fenêtres écrivent déjà par ce chemin. Après l'écriture, `signaler_import` appelle `MainWindow._on_import_complete` : récapitulatif dans l'historique, « Suggestions à valider », « Auto-complétés à vérifier ».

**Règles de l'import** (`src/utils/rapprochement_fiche/regles_import.py`, `planifier_import`, `LotReprise.planifier_par_regles`, `EnregistrementFicheService.planifier_par_regles`) : le tableau du § 10.12, sans question. Les écrans des PR 2 et 3 s'en serviront ; d'ici là, les fenêtres gardent leurs questions.

Écart au tableau du § 10.12, trouvé par la relance : **un appareil à créer dont la marque est inconnue n'est pas importé.** Créé sans marque, il n'était jamais retrouvé par la marque et la réf. : la relance le recréait (+42 appareils sur le 1ᵉʳ lot). L'auto-complétion lui donnait en plus la marque d'un autre appareil de même réf. (36 doublons Ikea).

**1ᵉʳ lot réel par les règles** (`scripts/mesurer_lot_reprise.py --regles-import`, copie de la base par l'API backup) :

| | Questions (§ 10.11) | Règles de l'import |
|---|---|---|
| Appareils créés | 1 262 | 1 357 |
| dont même marque et même réf. qu'un appareil existant | 0 | 0 |
| dont même réf. sous une marque hors du groupe | 0 (R4 « oui » simulé) | 95 (Beko / Altus, Bluesky, Far ; Ikea / Elica) |
| Créés sans type | 0 | 17 (16 avec une suggestion) |
| Liens créés | 25 343 | 25 343 |
| Lignes non écrites | 84 « à revoir » | 84 non importées (12 fiches), dont 46 de marque inconnue |
| Fiches sans code produit | reprises sous la réf. produit (R7 « reprendre » simulé) | 4 mises de côté |
| Écriture | 0,5 s | 12 s (une association à la fois, comme un PDF) |
| Croissance | +9,9 Mo | +10,4 Mo |
| Relance du même lot | 0 ajout | **0 ajout** |

**Points à trancher par l'utilisateur :**
- les 95 appareils de même réf. sous une marque hors du groupe. Ce sont les anciennes questions R4 ; la réponse est de compléter les groupes de marques (`groupes_marques`, `data/reprise_fiches.json`) ;
- les 46 lignes de marque inconnue ;
- la durée d'écriture : 12 s par lot, soit environ 27 min pour la reprise entière.

**Vérification :**
- `tests/unit/test_reprise_import.py` : doublon entre fichiers relié au 1ᵉʳ passage (le test échoue sans le correctif) ; fiche seule écrite par l'import puis relue sans ajout, récapitulatif transmis à la fenêtre ; lot des 3 fiches d'exemple par les règles puis relance sans ajout ; même réf. sous une marque du groupe reliée ; création hors du groupe au type auto-complété ; fiche sans code produit mise de côté ; appareil reconnu non modifié ; marque inconnue non importée.
- Les tests existants des deux fenêtres passent par le nouveau chemin d'écriture.
- Suite complète (2 036 tests), `compileall`, lancement de `run.py`.

### 10.14 Fiches « en vrac » : à refaire depuis les PDF (2026-11-13)

**Demande de l'utilisateur** : une fiche aux données en vrac est difficile à exploiter. L'outil relève la référence de la pièce et invite à chercher les PDF pour refaire la fiche proprement. Il ne doit jamais créer d'appareils aux références bancales, qui demanderaient une reprise quasi intégrale des données.

**Exemple donné** : fiche 7196, crochet portillon freezer `480131100599`. Le lecteur la croit propre (profil « Fiche standard », aucun passage incompris), mais chaque ligne colle le 12NC, le nom et une description :
- le nom devient « ARG18470A+ Réfrigérateur 1 » et le type de la ligne devient « Porte » (239 lignes sur 381) ;
- les modèles Ikea sont collés et coupés : « 902.537.43CF94A++RÉFRIGÉRAT » ;
- toute la liste prend la marque Whirlpool.

Par les règles du § 10.13, la fiche donnerait 360 liens sans risque, car l'appareil est retrouvé par son 12NC et l'outil garde son nom propre. Elle donnerait aussi **21 créations, toutes bancales**.

**Constat** : le danger d'une fiche en vrac vient des **créations**, pas des liens.

**Décisions de l'utilisateur (2026-11-13)** :
- fiche en vrac : les liens vers les appareils connus et les relations sont écrits ; **aucun appareil n'est créé** ; la fiche est notée « à refaire depuis les PDF » ;
- elle sort de la liste quand un import PDF ou CSV porte sur sa référence de pièce, ou par un bouton « Fait ».

**Mesures** :
- **Syntaxe, export complet** (lecteur seul) : 1 510 fiches ont au moins la moitié de leurs lignes illisibles. Ce sont des CSV collés tels quels (fiche 13306, « 34342020000,BAAN34VP,,,,Combi posable / Froid statique »), la marque prise pour la réf. (fiche 19025, « Liebherr » sur 1 817 lignes) et des paragraphes de codes. Ces lignes ne sont déjà jamais créées (réf. illisible). Certaines formes signalées sont saines, et un critère de syntaxe seul ratisse trop large : Liebherr « B 2756-20 001 », V-Zug « 00.206.005.02 », Rowenta « 460900 - ASPIRATEUR ».
- **Créations, 13 lots réels** (1 292 fiches, règles du § 10.13, rien d'écrit) : sur 37 886 créations, **767 douteuses (2 %)**, réparties dans **41 fiches** sur les 468 qui créent des appareils. Les critères, comptés sur la ligne à créer :

| Critère | Créations | Fiches | Exemple |
|---|---|---|---|
| nom mêlé d'une description d'appareil | 419 | 17 | `ARC5453 Combiné 1 groupe`, `WW1400/A Réfrigérateur 1` |
| n° d'article Ikea collé | 370 | 27 | `001.515.55HDDW00S`, `101.825.75MWN210SMICROWAVE-858779115771` |
| type de ligne qui n'est pas un appareil | 89 | 6 | `Porte` |
| mot collé ou coupé | 47 | 7 | `CF94A++RÉFRIGÉRAT` |

- Part des créations douteuses dans ces 41 fiches : **15 fiches à 50 % ou plus** (7409 : 180 sur 180 ; 7196 : 21 sur 21), 4 fiches entre 20 et 50 %, et 22 fiches sous 20 %. Ces dernières sont souvent de grandes listes propres avec quelques Ikea : 8161, 30 sur 4 042 ; 7876, 66 sur 880.
- Vu aussi : des marques bancales tirées d'un en-tête (« PROFESSIONNELS HOTTE », fiche 8143). Ce critère est à ajouter : une marque inconnue de l'outil.

**Décidé (seuil de 20 % accepté le 2026-11-13), fait dans la PR 2 (§ 10.15)** :
- une fiche est **en vrac** quand au moins 20 % de ses créations sont douteuses. Elle n'a alors aucune création et passe « à refaire depuis les PDF » ;
- sous ce seuil, seules les lignes douteuses ne sont pas créées. La fiche est aussi notée « à refaire », avec le nombre de lignes concernées ;
- la liste « Fiches à refaire depuis les PDF » donne, pour chaque fiche : la réf. de la pièce, le n° du produit, le lien vers la page du site, la raison, des exemples, et un export CSV ;
- les critères vivent avec le lecteur et le rapprochement. La fiche seule (PR 2) les affiche dans un bandeau, le lot (PR 3) dans sa liste.

### 10.15 Fiche seule par la fenêtre d'import, fiches à refaire — refonte, PR 2 (2026-11-13)

**« Lire une fiche du site »** (`src/ui/fiche_site_import.py`) :
- `SaisieFicheSite` demande le lien ou la description. La fiche est lue puis planifiée par les règles (`EnregistrementFicheService.fiche_a_importer`), sans question.
- `ouvrir_import_fiche` ouvre ensuite la fenêtre d'import habituelle (`ImportDialog`) sur un fichier `FICHE_SITE` qui porte la fiche (`ImportFile.fiche`, `FicheAImporter`).
- Dans la fenêtre d'import, la fiche ne demande pas de choix de colonnes. L'aperçu est en langage métier (déjà liés, connus, à créer, non créés « à refaire », couverts, non importés), et un bandeau orange signale une fiche à refaire. La référence de la pièce se saisit s'il n'y a pas de code produit. Le libellé proposé est celui de l'outil, ou le titre coupé. La Succession est préremplie avec les anciennes références, la remplaçante et les équivalentes de la fiche.
- **Importer** passe par `ImportManager.importer_avec_dialogue` :
  - `preparer` remet les saisies dans le plan (`FicheAImporter.appliquer_saisie`). Une relation retirée n'est pas écrite ; une équivalente retirée est **écartée** (`decisions_references`) ; une relation ajoutée est écrite ;
  - l'import réel est ensuite celui d'un PDF (`_launch_real_import`, progression, sauvegarde du jour) ;
  - en fin d'import : noms commerciaux vides complétés, `MainWindow._on_import_complete` (historique, suggestions, auto-complétés), puis la pièce dans la recherche.
- **Lien collé dans le tableau** (Cmd+V) : un lien de 1001pieces.com (`est_lien_fiche_site`) ouvre cette saisie et lit la fiche aussitôt.
- `FicheSiteDialog` ne sert plus qu'à « Ouvrir la fiche… » dans l'import par lots (PR 3).

**Fiches en vrac** (`regles_import.retenir_creations_douteuses`, `motifs_douteux`) :
- Cinq critères sur la ligne à créer :
  - le nom mêlé d'une description (types et appellations de l'onglet Appareils, plus « armoire », « encastrable », « statique », « combiné », « 1 porte »…) ;
  - un n° d'article collé (`999.999.99` suivi d'autre chose) ;
  - un mot collé ou coupé (« …A++RÉFRIGÉRAT ») ;
  - un type écrit sur la ligne qui n'est pas un appareil (« Porte ») ;
  - une marque inconnue de l'outil (`AppareilRapproche.marque_inconnue`, posé par le rapprochement).
- À partir de 20 % de créations douteuses (`SEUIL_VRAC`), la fiche est en vrac : aucune création. Sous ce seuil, seules les créations douteuses sont retenues.
- Dans un lot, une ligne retenue dont l'appareil est créé proprement par une autre fiche partage cette création ; sans cela, la relance ajouterait un lien.
- **Mémoire** : table `fiches_a_refaire` (réf. de la pièce, n° du produit, raison, en vrac, créations, retenues, exemples, date). Elle suit le renommage et la suppression de la pièce. Le récapitulatif de l'import liste les fiches à refaire (« [!] Fiche … à refaire depuis les PDF »).
- **Sortie de la liste** : `ImportManager._solder_fiches_a_refaire`. Tout import PDF, CSV ou collage d'une référence notée la retire de la liste, et le récapitulatif l'annonce. Le bouton « Fait » et l'écran de la liste viennent avec la PR 3.

**Mesures** (copies de la base, API backup) :
- 13 lots (1 292 fiches), plan par les règles : **93 fiches à refaire, dont 69 en vrac**, et 16 251 créations retenues.
  - Le critère « marque inconnue » en retient 9 043. Ce sont surtout des **en-têtes de série pris pour des marques** : « ALPINETRK » (fiche 7294, 4 113 appareils qui auraient été créés sous cette fausse marque), « AWZCLASSICCT », « GSFEXWS », « GSFSYMPHONY », qui sont des séries Bauknecht.
  - Il retient aussi quelques vraies petites marques (« Chromex », « Dilem ») : leurs fiches passent « à refaire ».
- Lots 1 à 3 écrits : 1 323, 510 et 267 appareils créés ; aucun doublon de même marque et même réf. ; 14 fiches à refaire (11 en vrac) ; relance du lot 1 seul **sans ajout**.
- Fiche 7196 : 0 appareil créé (21 auparavant, tous bancals), 360 liens vers les appareils connus.

**Vérification** :
- `tests/unit/test_fiche_import_ecran.py`, rendus hors écran :
  - 7285 par la fenêtre d'import (aperçu, Succession préremplie, équivalente retirée puis écartée, import réel, relue sans ajout) ;
  - 7196 en vrac (bandeau, aucune création, fiche notée, puis retirée par un collage de sa référence) ;
  - lien reconnu ;
  - Cmd+V d'un lien.
- `test_reprise_import.py` adapté (base construite avec Bauknecht).
- Suite complète (2 040 tests), `compileall`, lancement de `run.py`.

### 10.16 Lot en cartes, fiches à refaire, fenêtre simplifiée — refonte, PR 3 (2026-11-13)

**« Importer les fiches du site »** (`src/ui/reprise_site_dialog.py`, réécrite). La fenêtre garde ce qui est propre au massif :
- les deux exports, avec « Repartir de zéro » ou « Continuer » ;
- l'avancement : dernier produit, lots, fiches mises de côté, fiches à refaire ;
- la taille du lot et « Lire le lot suivant », en thread, avec « Arrêter ».

Le lot lu est planifié par les règles de l'import (`RepriseSiteService.planifier_lot`), puis `ouvrir_import_lot` ouvre la **fenêtre d'import habituelle**, une carte par fiche (import de plusieurs fichiers) :
- la carte porte : la case « importer » (décochée = mise de côté), la référence de la pièce (à saisir sans code produit), le libellé, Obsolète, le résumé des appareils, l'alerte « à refaire », les relations (Remplace, Équivalentes, Remplacée par, retirables) et le lien « n° … sur le site » ;
- en tête : le total du lot et un bandeau pour les fiches à refaire ;
- pas de référence commune ni de zone de groupes : les relations sont propres à chaque fiche.

« Importer » passe par `RepriseSiteService.preparer_import_lot` :
- les saisies des cartes entrent dans les plans (`FicheAImporter.appliquer`) ;
- l'import réel est celui d'un PDF (worker, progression) ;
- `fin_import` clôt le lot sur le thread principal : journal, fiches de côté, avancement.

Fermer la fenêtre d'import sans importer n'écrit rien et ne fait pas avancer l'import. Les onglets à questions (« À décider », « Fiches du lot », « Toutes les lignes ») disparaissent de l'écran. Le moteur de questions, `FicheSiteDialog` et `questions_reprise.py` ne sont plus appelés par l'interface ; leur retrait est l'objet de la PR 5.

**Fiches sans code produit** (demande de l'utilisateur, 2026-11-13) : elles ont une carte, décochée tant que la référence n'est pas saisie.
- Le libellé est repris du titre de la fiche, sinon du nom du produit de l'export, sans sa réf. finale et coupé au type (`FicheAImporter._libelle_du_nom`).
- Le lien vers la fiche sur le site (`lien_site`) permet de trouver la référence. Il figure aussi dans le bandeau de la fiche seule.
- La référence interne n'est jamais prise par défaut comme pièce.

**« Fiches à refaire »** (`src/ui/fiches_a_refaire_dialog.py`) : un bouton dans la fenêtre du lot et le menu « Données → Fiches du site à refaire… ».
- La liste montre la réf. de la pièce, le n° du produit, la raison, des exemples et la date.
- On y trouve « Ouvrir la page du site », « Fait » et « Exporter en CSV… » (`ecrire_csv`, lien du produit inclus).

**« Lire une fiche du site » simplifiée** (demande de l'utilisateur, 2026-11-13) : une seule zone de texte et « Lire ». Un lien seul (`est_un_lien`) est téléchargé ; tout autre texte est lu comme la description.

**Marques inconnues** (mesure sur 13 lots) : sur 285 « marques » inconnues de l'outil, 277 sont des en-têtes de série pris pour des marques (ADGSPACEWH, DDSEALINE, GSFSYMPHONYACTIV, PROFESSIONNELS HOTTE…), soit 9 183 lignes. Il reste 8 vraies marques ou fautes de frappe (BAUKNCHT, Séverin, Airfoce, Dilem, Braun…) pour 45 lignes. La règle est gardée : créer « BAUKNCHT » serait pire. Une vraie marque nouvelle se crée à la main ou par un import PDF.

**1ᵉʳ lot réel par le chemin de la fenêtre** (`preparer_import_lot`, puis l'import, puis `fin_import`, copie de la base) :
- 100 cartes ouvertes en 0,9 s ;
- 1 323 appareils, 25 309 liens, 91 remplacements, 198 membres d'équivalence, 96 produits du site, 2 fiches à refaire, 4 fiches sans code produit de côté ;
- 10 s d'import ; **relance sans ajout**.

**Vérification** :
- `test_reprise_site.py` :
  - lot en cartes, avec une carte décochée, une référence saisie, le libellé et le lien de la fiche sans code produit, puis la relance sans ajout ;
  - fenêtre d'import fermée sans rien écrire ;
  - liste à refaire (Fait, export CSV).
- `test_ecarts_ecrans.py` : un lot par les règles garde les valeurs de l'outil.
- `test_fiche_import_ecran.py` : zone unique, lien ou description.
- Suite complète, `compileall`, lancement de `run.py`.

### 10.17 Référence associée Whirlpool / Indesit / Beko — refonte, PR 4 (2026-11-13)

**Pour tous les imports** (PDF, CSV, collage, fiche seule, lot de fiches) :
- `src/utils/rapprochement_fiche/associee.py` : `origine_associable(ref)` rend Whirlpool, Indesit ou Beko d'après la table des formats (§ 5.5, configuration lue sans jamais être écrite), sinon `''`.
- `src/ui/champ_reference_associee.py` (`ChampReferenceAssociee`) : le champ « Réf. associée », une référence facultative, **à droite de la référence de la pièce** (demande de l'utilisateur, 2026-11-13 : le rapprocher de la référence incite à le compléter). Il se place sur la ligne « Réf. » du fichier seul, et à côté de la référence de chaque carte de plusieurs fichiers ou de fiche. Il n'apparaît que pour une pièce de l'un des trois groupes. Il suit la référence saisie (collage, fiche sans code produit) et se préremplit ainsi :
  - la réponse mémorisée ;
  - sinon l'équivalente de ligne 0 de la pièce ;
  - sinon, pour une fiche du site, la 2ᵉ réf. de son code produit (`FicheAImporter.reference_associee`).
- **Pas de case « aucune »** (décision de l'utilisateur, 2026-11-13) : le champ ne bloque rien, et laissé vide il n'écrit rien. La table garde la possibilité d'une réponse « aucune » (NULL), que l'interface n'écrit pas.
- `ImportConfiguration.references_associees` (réf. de la pièce → référence associée), recueillie seulement pour la référence que la pièce aura vraiment. L'import l'applique en fin de finalisation, après les écritures propres aux fiches (`ImportManager._appliquer_references_associees`) ; le récapitulatif porte `references_associees`.
- **Mémoire** : table `references_associees(ref_piece, associee, decide_le)`. Elle suit le renommage et la suppression de la pièce. Une référence associée devient une équivalente de la pièce, marquée ligne 0 (code produit de la Fiche complète, § 8.1) avec sa marque d'origine. **Écart au § 10.12** : « aucune » ne va pas dans `decisions_references`, dont la contrainte `CHECK (nature IN ('ecartee', 'origine'))` ne s'étend pas sans recréer la table ; une petite table dédiée est plus simple et plus claire.
- **Fiche complète** (correctif du 2026-11-13, retour de l'utilisateur) : la référence associée retenue va **à la suite dans le code produit** (« Code produit : C00138863 482000029398 »), même pour une pièce sans produit du site (importée par PDF), et dans les deux sens (`references_associees_de`, `FicheProduitService.references_fiche`) ; elle sort des références équivalentes. Avant, seule une pièce vendue sur le site recevait sa paire. Dans la fenêtre d'import, le champ suit directement la référence de la pièce (plus de vide entre les deux).
- Retouche : les libellés de la section Succession passent de 220 à 240 px (« Cette réf. est remplacée par » n'est plus coupé) ; `RefChipsInput.definir_aide`.

**Vérification** :
- `tests/unit/test_reference_associee.py` :
  - formes des trois groupes ;
  - mémoire (équivalente de ligne 0, « aucune », renommage) ;
  - collage avec réponse retenue puis reproposée, champ laissé vide (rien de retenu), pièce BSH sans champ ;
  - cartes de plusieurs fichiers ;
  - fiche 7285 préremplie avec `C00319033` et mémorisée après l'import ;
  - rendu hors écran.
- Suite complète (2 048 tests), `compileall`, lancement de `run.py`.

### 10.18 Export EveryParts des fiches reprises — pistes (2026-11-13)

**Demande de l'utilisateur** : les fiches récupérées du site, seules ou par lot, doivent pouvoir donner un export EveryParts. La 1ʳᵉ colonne (`product`) porte la référence produit du site (`.product-reference`). C'est l'objectif secondaire de la reprise, en plus de consolider le catalogue. Il faut une petite fenêtre d'export des fiches récupérées.

**Ce qui existe déjà** :
- le format CSV EveryParts de la configuration des exports : `product` = `{export_ref}`, puis type, marque, modèle, réf. modèle, nom commercial ; fichier `{export_ref}_everyParts.csv` ;
- `{ref_interne}` et `{id_product}` dans les colonnes et le nom de fichier (§ 10.10) ;
- la `.product-reference` de chaque fiche reprise, gardée dans `produits_site.ref_interne` avec la pièce et le n° du produit ;
- l'écriture d'une ligne par appareil (`ExportManager._execute_csv_export`, `render_csv_row_with`).

**Pistes, de la plus simple à la plus complète** :
1. **Fenêtre « Exporter les fiches reprises (EveryParts) »** (menu Données). Elle liste les produits du site gardés : réf. produit, n° du produit, pièce, nombre d'appareils, date de reprise, déjà exportée ou non. Elle filtre par « pas encore exportées », par lot ou par date, puis exporte la sélection vers un dossier. Chaque fiche passe par le CSV EveryParts de la configuration, avec `{export_ref}` = la réf. produit du site. Rien de nouveau à paramétrer.
2. **Un fichier par fiche, ou un seul fichier pour la sélection** : la colonne `product` portant la réf. du produit sur chaque ligne, un fichier unique peut contenir plusieurs produits. Le choix se fait par une case dans la fenêtre.
3. **Mémoire de l'export** : une colonne `exporte_le` sur `produits_site`, pour ne réexporter que les nouveautés, ou une fiche dont des appareils ont été ajoutés depuis (date du dernier lien de la pièce).
4. **Raccourci en fin de lot** : « Exporter ce lot vers EveryParts » à la fin de l'import d'un lot (piste 1, filtrée sur le lot).

**Tranché (2026-11-13)** :
- appareils de la pièce **et de ses anciennes références** (décision de l'utilisateur) ;
- un fichier par fiche, ou un seul : au choix dans la fenêtre ;
- une pièce vendue par plusieurs produits : un jeu de lignes par produit.

Pistes 1 à 3 faites au § 10.19 ; la piste 4 (raccourci en fin de lot) reste possible.

### 10.19 Export EveryParts des fiches reprises — fait (2026-11-13)

- **Service** `src/services/export_fiches_reprises_service.py` (`ExportFichesReprisesService`) :
  - `produits(non_exportes)` lit `produits_site_reprises` : les produits par n° ; « à exporter » = jamais exportés, ou relus (`lu_le`) depuis le dernier export ;
  - `lignes(ref_piece)` : les appareils de la pièce et de ses anciennes références (`get_all_predecessors`), une fois chacun ;
  - `exporter(produits, dossier, un_seul_fichier)` : le format CSV de la configuration (`get_csv_settings`, `render_csv_row_with`, assainissement des formules), avec `{export_ref}` = la référence produit du site et `{ref_interne}` / `{id_product}` disponibles. Le nom vient du modèle de la configuration (`fiches_reprises` pour un seul fichier). Un produit sans appareil n'est pas exporté, mais il est compté. La date d'export est gardée : nouvelle colonne nullable `produits_site.exporte_le`, `marquer_produits_exportes`.
- **Fenêtre** `src/ui/export_fiches_reprises_dialog.py` (`ExportFichesReprisesDialog`) :
  - filtre « à exporter » ou « tous », recherche ;
  - la sélection est exportée (sans sélection, toute la liste) ;
  - case « un seul fichier », dossier des exports (« Changer… », « Ouvrir le dossier ») ;
  - export dans un thread, avec progression ;
  - récapitulatif dans l'historique.
- **Accès** : menu « Données → Exporter les fiches reprises (EveryParts)… » et bouton « Exporter vers EveryParts… » de la fenêtre « Importer les fiches du site ».
- **Vérification** (`tests/unit/test_export_fiches_reprises.py`, extrait de la vraie base, les 3 fiches d'exemple reprises) :
  - 20744 : 450 lignes, qui viennent toutes de ses 4 anciennes références, en-tête de la configuration, `GAU11051894` en 1ʳᵉ colonne ;
  - 20746 : 831 lignes ;
  - un seul fichier ;
  - plus rien « à exporter » après l'export ;
  - fenêtre rendue hors écran, export d'une sélection dans le thread.
- Suite complète, `compileall`, lancement de `run.py`.

### 10.20 Retraits : moteur de questions, catégories, écarts — refonte, PR 5 (2026-11-13)

La refonte du § 10.12 est complète. L'interface n'appelait plus le moteur de questions depuis la PR 3 ; il est retiré avec ce qui ne servait qu'à lui :
- **fichiers supprimés** : `src/utils/reprise_site/questions.py` (R1 à R7, Q1 à Q7, `QuestionnaireLot`), `src/ui/questions_reprise.py` (panneau), `src/ui/fiche_site_dialog.py` (ancienne fenêtre de fiche et de « fiche du lot »), et les styles des cartes de questions et des écarts (`StyleManager`) ;
- **plan d'écriture** (`decisions.py`) : plus de catégories ni d'états (validée, laissée de côté, en attente), ni de « type commun ». Sans choix, chaque élément suit sa proposition. Les choix ligne par ligne (`ChoixAppareil`), les doutes d'identité et les équivalentes écartées restent : ce sont eux que posent les règles de l'import (`regles_import.py`). `categorie_appareil` reste, pour dire ce qu'une ligne demande ;
- **lot** (`lot.py`) : plus de résumé par catégorie, de groupes de doutes, de profils ambigus mis de côté, de fiches personnalisées ni de fiches « à revoir » (partielles). Restent l'analyse, les fiches mises de côté, le plan par les règles (créations partagées entre fiches, fiches en vrac retenues) et les mesures ;
- **service de reprise** : plus de questionnaire, de relecture après une règle de groupe, ni de règles mémorisées. `chemin_configuration` est retiré, et rien n'écrit plus `data/reprise_fiches.json` ;
- **configuration** : plus de `regles_reprise` ni d'`enregistrer_configuration`. Un fichier du poste qui en contient encore est lu sans elle : seules les clés connues comptent. Sur le poste de l'utilisateur, ce sont R5 « enregistrer » et R6 « garder », les règles appliquées désormais d'office ;
- **écarts outil / site** : le rapprochement relève toujours les champs qui diffèrent. L'import garde la valeur de l'outil, et ne complète qu'un nom commercial vide (`plan.maj_appareils`). La table `decisions_champs` n'est plus écrite ; elle reste lue, sans effet sur l'import ;
- **script de mesure** : `scripts/mesurer_lot_reprise.py` décide toujours par les règles (plus de `--questions` ni de « tout valider »).

**Vérification** :
- Tests réécrits pour le plan par les règles : `test_reprise_site.py`, `test_enregistrement_fiche.py`, `test_ecarts_fiche.py` (nom vide complété, valeurs de l'outil gardées), `test_reprise_rien_de_faux.py`, `test_fiche_export_site.py`.
- Tests retirés avec ce qu'ils testaient : `test_reprise_questions.py`, les écrans à questions, la forme des réf. internes groupées. Le test « un lot par les règles garde l'outil » passe dans `test_reprise_import.py`.
- **1ᵉʳ lot réel** (copie de la base) : mêmes chiffres qu'avant les retraits (1 323 appareils, 25 309 liens, 91 remplacements, 198 membres d'équivalence, 96 produits, 2 fiches à refaire) ; **relance sans ajout**.
- Aller-retour des 3 fiches d'exemple ; suite complète (2 040 tests), `compileall`, lancement de `run.py`.

### 10.21 Référence principale : « ⇄ » à l'import, ordre fixe dans la Fiche complète (2026-11-13)

**Demande de l'utilisateur** : de temps en temps, la référence importée (nom du PDF, code produit) n'est pas la référence principale de la paire Whirlpool / Indesit / Beko. Il faut pouvoir définir la principale facilement. Décision : un bouton « ⇄ » à l'import, et l'ordre fixe dans la Fiche complète.

- **« ⇄ »** (`ChampReferenceAssociee.inverser`, `ImportDialog._inversion`). Le bouton se place entre la référence de la pièce et la réf. associée, et n'apparaît qu'avec une réf. associée saisie. Il est présent dans le fichier seul, les cartes de plusieurs fichiers et les cartes de fiches. Un clic échange les rôles :
  - la réf. associée devient la référence de la pièce : elle reçoit les appareils, le libellé, Obsolète et, pour une fiche du site, le produit du site ;
  - la référence d'origine devient l'associée ;
  - pour un champ de saisie (collage, fiche sans code produit), son texte change ; pour une référence fixe (nom du fichier, code produit), elle est remplacée pour cet import (`_refs_inversees`, lu par `_ref_du_fichier` et `_collecter_fiches`) et l'étiquette l'indique ;
  - un second clic revient au point de départ ;
  - pour une fiche du site, la nouvelle principale sort de ses propres équivalentes.
- **Mémoire** : `references_associees(principale → associée)`, dans le sens choisi.
- **Ordre fixe** (`reference_principale_de`, `FicheProduitService.references_fiche`) : la principale vient toujours en premier dans le code produit, que l'on recherche la principale ou l'associée.
- **Limite** : dans l'import de plusieurs fichiers, les tuiles de la zone « Relations entre références » gardent la référence du nom de fichier ; l'inversion vaut pour la pièce, les appareils et la paire.

**Vérification** :
- `test_reference_associee.py` : inversion dans un collage et dans un fichier (appareils sur la principale, code produit identique quelle que soit la référence recherchée, double clic qui revient au départ, rendu hors écran), fiche 7285 inversée (pièce `C00319033`, produit du site et liens dessus, `481073071153` équivalente).
- Suite complète (2 045 tests), `compileall`, lancement de `run.py`.

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
| Masse | lots de 100, un import de plusieurs fichiers (une carte par fiche), règles de l'import sans question, reprise d'une session à l'autre, fiches à refaire depuis les PDF (§ 10.12 à 10.20) |
| EAN | conservé avec le produit du site, le site fait foi |
| Référence interne | gardée pour chaque produit du site (avec `id_product`), proposée à l'export EveryParts |
| Retour vers le site | gabarits Fiche complète, une ligne par origine, paire, « Remplace » dans l'ordre de la fiche (`rang_fiche`) |
| Libellé de la pièce | titre de la fiche coupé avant « pour <type> » (onglet Appareils), caractéristique chiffrée gardée |
| Appareil connu, champ différent | relié ; la valeur de l'outil est gardée, un nom commercial vide est complété (§ 10.20) |
