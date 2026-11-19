# Restitution : l'agent recommandé et pourquoi

Appuyée sur `equipe/analyse/comparatif-couches.md`, `equipe/TRAVAIL.md` et
`equipe/RECAP-2026-11-18.md`. Tous les chiffres viennent des traces et des mesures du dépôt.

## 1. Ce qu'on recommande

L'agent **en couches**, tel qu'il est dans `equipe/agent.py` : portier hors sujet, routeur,
cache, traducteur, puis l'agent complet en dernier recours, avec deux outils (`calculer`,
`chercher_colonne`) et cinq étapes au plus.

Pourquoi :

- **Il répond juste.** 26 sur 26 sur la batterie de référence et 30 abstentions fondées sur 30,
  17 sur 17 sur une batterie de tournures neuves (passes du 18 novembre, sans cache).
- **Il coûte peu.** 0,000457 $ la question sur la batterie de référence, contre 0,0017 $ au départ
  pour un `CodeAgent` nu. Sur 75 questions, 75 % n'appellent pas l'agent complet.
- **Il est reproductible là où ça compte.** Le portier, le routeur, le cache et le traducteur
  donnent la même réponse à chaque fois ; c'est l'agent complet, 25 % des questions et 89 % du
  coût, qui change d'une passe à l'autre.
- **Il s'abstient plutôt que d'inventer.** Une abstention n'est pas une panne : la justification
  dit ce que le fichier ne permet pas de dire.

Ce qui reste à démontrer : le choix de la **variante** de l'agent complet (`ouvert`, `ferme`,
`outils`). Aucune mesure ne les compare (voir la fin du comparatif). La variante livrée est
`ouvert`, qui exécute sur la machine du code écrit par un modèle. Tant qu'une passe `ferme` ou
`outils` n'a pas montré les mêmes scores, la recommandation est de garder `ouvert` en le disant,
et de présenter la fermeture comme une réduction des droits, jamais comme un bac à sable.

## 2. Sécurité, en trois phrases

Le filtre que le modèle écrit est lu par deux expressions régulières puis appliqué par des
comparaisons pandas : ni `eval`, ni `exec`, ni `query` (tests `test_aucun_eval_exec_query` et
`test_filtre_malveillant_refuse`). Un outil rend une phrase courte, jamais le tableau, et les
groupes sont limités à dix. Les deux lignes qui ouvrent l'accès aux données restent visibles dans
`agent.py`, et la fermeture ne protège pas complètement : la seule isolation réelle est une machine
distante.

## 3. Démonstration avec des questions d'allergologue

Chaque question vient des batteries de l'équipe. On lance la commande en direct et on lit la
réponse ; la colonne « Couche » dit ce qui doit se passer, d'après la passe de 75 questions.

    uv run kit agent "<question>"

| Ordre | Question | Couche | Coût | Ce qu'elle montre |
|---|---|---|---|---|
| 1 | Combien de patients sont inclus dans le jeu de données ? | routeur | 0 $ | une réponse instantanée, sans modèle |
| 2 | Combien de patients bénéficient d'un traitement contre la rhinite ? | traducteur | 0,0002 $ | le modèle choisit l'opération, le code calcule |
| 3 | Combien de patients sont sous biothérapie pour leur asthme ? | traducteur | 0,0002 $ | les codes à plusieurs valeurs sont lus par l'outil |
| 4 | Chez les patients de moins de 18 ans, quel est le taux de sensibilisation des hommes comparé à celui des femmes ? | traducteur | 0,0003 $ | une comparaison par groupe, avec les effectifs |
| 5 | Combien de patients présentant des symptômes cutanés sont traités pour une rhinite ? | agent complet | ~0,005 $ | le dernier recours : plus lent, plus cher |
| 6 | Quelle est la concentration moyenne de Bet_v_1 en kUA/L ? | agent complet | ~0,004 $ | l'unité n'est pas dans le fichier : l'agent doit s'abstenir (cette question avait donné une réponse inventée avant la correction du 18 novembre) |
| 7 | Les patients ayant un dosage Der_p_1 élevé présentent-ils un risque accru de développer un asthme ? | agent complet | ~0,001 $ | une question de pronostic : abstention |
| 8 | Quelle est la capitale du Japon ? | portier | 0 $ | le hors sujet est refusé sans jeton |

À dire pendant la démonstration : le temps et le coût sont affichés après chaque réponse, une
abstention est un résultat et non une erreur, et relancer une question déjà posée la sert depuis le
cache à 0 $ (`ALLERGYLAB_SANS_CACHE=1` pour mesurer sans).

Les questions 5 à 7 passent par l'agent complet : prévoir 5 à 25 secondes et ne pas les enchaîner
si la cagnotte est serrée.

## 4. Limites à dire à voix haute

- Une question ambiguë est tranchée par le système : deux questions de la batterie ont deux lectures
  défendables, la note porte une tolérance.
- Un fichier étranger qui reprendrait nos noms de colonnes avec un autre codage serait lu avec notre
  codebook et répondrait faux sans le dire.
- Les réglages ne sont validés que sur Haiku. Sonnet n'a eu que 6 questions.
- `kit bilan` donne un plancher de la consommation : un appel interrompu peut être facturé sans trace.
- Les trois comparaisons à trois groupes (famille C) montent encore vers l'agent complet, à environ
  0,005 $ pièce.
