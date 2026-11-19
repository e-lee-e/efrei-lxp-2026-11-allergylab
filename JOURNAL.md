# Journal de bord

Une phrase par jour au moins, signée de l'équipe, jamais d'un prénom. Le nombre d'appels réels est compté dans `traces/appels/<jour>/` : un appel est réel quand il a consommé des jetons, les autres ont été servis sans modèle (cache, portier, routeur).

## Lundi 16 novembre

Équipe 2. Installation du kit et premier essai de l'agent livré : 1 appel réel.

## Mardi 17 novembre

Équipe 2. 341 questions tracées, dont 251 appels réels au modèle de développement ; le reste est servi sans modèle.

- Décision : plus de seuil de taille de groupe. Il est retiré de `consigne.md` (commit 177300c) : un petit groupe est une question légitime, l'agent répond avec le nombre de patients retenus et le chercheur juge.
- Décision : cinq outils réduits à deux (`calculer`, `chercher_colonne`), commit 2c0ad37. La description de chaque outil est repayée à chaque étape ; `taux_par_groupe`, `taux_par_presence` et `positifs` sont des cas de `calculer`.
- Décision : plafond de cinq étapes par question, fixé par C après mesure. Huit étapes coûtaient jusqu'à 0,008 $ une question.
- Piège : le code 9 ne vaut « non renseigné » que dans les colonnes de `CODEES` (`equipe/outils/_filtre.py`). Dans `Age`, les mois et les dosages, 9 est une valeur.
- Piège : une cellule « 1,3 » porte deux codes. L'outil la lit, code exact (« 1 » ne se trouve pas dans « 10 ») ; la convertir en nombre jetait des patients, cause de deux réponses fausses.

## Mercredi 18 novembre

Équipe 2. 24 questions tracées, dont 12 appels réels ; la journée a surtout servi aux batteries du harnais d'évaluation (voir `equipe/RECAP-2026-11-18.md`).

## Jeudi 19 novembre

## Vendredi 20 novembre

## Demandes de rallonge

Aucune demande à ce jour.
