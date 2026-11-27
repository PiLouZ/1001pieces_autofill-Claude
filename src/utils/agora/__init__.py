"""
Branchement de l'outil sur Agora (AgoraPlus, plateforme SAV des constructeurs).

Deux sources, de coût très différent :
- les **fichiers MySpace** (téléchargés à la main sur myspace2.agoraplus.com,
  un par constructeur) : désignation, pièce commandable ou non, chaîne des
  remplacements, référentiel des appareils (marque, désignation). Lus en local,
  ils ne consomment aucun appel (`myspace`) ;
- l'**API** : appareils compatibles d'une pièce et prix (`client`). La licence
  d'EMG permet 10 appels par jour et par service, remis à zéro à minuit UTC :
  chaque réponse est gardée en cache et le compteur est tenu en local.

Tout est rangé dans une base à part, `data/agora.db` (non suivie par git,
régénérable) : la base des appareils n'est pas touchée avant l'import.
Les lignes d'appareils obtenues passent par l'import habituel (`conversion`).
"""
