# Le travail de l'équipe, chiffré

Ce document rassemble les mesures qui ont guidé nos décisions. Tous les chiffres
viennent de `traces/appels/` et de `equipe/mesures/`, sur le modèle de
développement (Haiku 5.5), avec `ALLERGYLAB_SANS_CACHE=1` pour chaque passe de
mesure. Aucun chiffre n'est estimé à la main.

## 1. L'architecture retenue

Une question traverse quatre couches, de la moins chère à la plus chère. Ce qui
n'est pas reconnu descend d'un étage.

| Ordre | Couche | Coût d'une question | Temps | Ce qu'elle fait |
|---|---|---|---|---|
| 1 | cache | 0 $ | 0,01 s | relit une réponse déjà donnée |
| 2 | portier hors sujet | 0 $ | 0 s | refuse ce qui ne parle pas du fichier |
| 3 | routeur | 0 $ | 0 s | reconnaît une dizaine de formes, calcule en Python |
| 4 | traducteur | 0,00017 à 0,00025 $ | 2 s | le modèle choisit une opération, le code calcule |
| 5 | agent complet | 0,0017 à 0,006 $ | 7 à 23 s | dernier recours : le modèle écrit du code |

## 2. L'évolution du coût par question

| Étape du travail | Coût | Écart |
|---|---|---|
| Départ, `CodeAgent` sans outils | 0,001715 $ | référence |
| Outils offerts mais ignorés par le modèle | 0,002576 $ | **+50 %** |
| Outils routés dans la consigne, format d'étape corrigé | 0,001594 $ | −7 % |
| Outil `taux_par_presence` (question de la rhinite) | 0,001665 $ | **−46 %** sur cette question |
| Routeur : questions reconnues | 0 $ | −100 % |
| Traducteur : requête canonique | 0,0002 $ | ÷ 10 |
| Cumul mesuré sur 12 questions | 0,000644 $ | **−62,4 %** |

Deux lois expliquent tout le reste : environ **5 000 jetons au premier appel** et
**7 000 par étape supplémentaire**, le contexte entier étant renvoyé à chaque
fois. La consigne a donc été compressée de 2 040 à **1 441 jetons** (−29 %), et
les étapes ont été supprimées avant les mots.

## 3. La batterie extérieure : 40 questions

Quatre familles de pièges, huit questions chacune, plus une famille propre.

| Famille | Ce qu'elle teste | Justes | Gratuites | Coût | Par question |
|---|---|---|---|---|---|
| A | question propre, réponse dans le fichier | 8/8 | 4 | 0,0008 $ | 0,00010 $ |
| B | même intention, mal écrite | 8/8 | 4 | 0,0009 $ | 0,00011 $ |
| C | filtres multiples | 8 formes justes, 1 valeur fausse | 0 | 0,0286 $ | **0,00357 $** |
| D | vocabulaire du domaine, réponse absente | 8/8 | 0 | 0,0153 $ | 0,00192 $ |
| E | hors sujet | 8/8 | 8 | 0 $ | 0 $ |
| **Total** | | | **16/40 (40 %)** | **0,0456 $** | |

La famille C pèse **20 % des questions et 63 % du coût**. C'est aussi la seule
dont les réponses changent d'une passe à l'autre.

## 4. Les erreurs trouvées, et leur cause

| Question | Réponse donnée | Vérité | Cause |
|---|---|---|---|
| A07 | 422 | **430** | une cellule `"1,3"` convertie en nombre : 8 patients jetés |
| C04 | 210 | **211** | même cause |
| C02 | abstention | **30,22** | « biothérapie » jamais reliée aux codes 6 à 8 |
| D03 | 2351 | abstention | le reformulateur local avait inventé un sujet |
| C08 | 157 / 79 | **26 / 20** | non-déterminisme du modèle entre deux passes |

Trois de ces cinq erreurs sont des erreurs de **sémantique des données**, pas de
compréhension de la phrase. C'est pourquoi le chantier n'est pas un modèle plus
gros, mais des outils qui lisent les données correctement.

## 5. Les tests

100 tests, aucun ne touche au réseau ni au modèle.

| Fichier | Tests | Ce qu'il couvre |
|---|---|---|
| `test_outils_agent.py` | 35 | `calculer`, `chercher_colonne`, filtres |
| `test_routeur.py` | 27 | routes, sac de mots, élisions, refus |
| `test_hors_sujet.py` | 13 | le portier |
| `test_agent.py` | 9 | les trois variantes, plafond d'étapes |
| `test_outils.py` | 9 | taux, présence, positifs |
| `test_traducteur.py` | 7 | requête canonique et exécution |

## 6. Le budget

| | |
|---|---|
| Cagnotte | 1,00 $ |
| Dépensé, tracé | 0,1415 $ (134 appels) |
| Deux passes antérieures au branchement des traces | ~0,05 $ |
| **Total réel estimé** | **~0,19 $** |

Le prix d'une question sur Sonnet vaut environ **20 fois** celui mesuré ici. Une
passe officielle de 40 questions coûterait donc **~0,91 $** : c'est précisément
là que les −62 % servent.

## 7. Ce qu'on a abandonné, et pourquoi

**Le reformulateur local (qwen3:0.6b, 522 Mo).** Sur les 40 questions : le routeur
seul en route 8, le routeur avec le modèle en route 8 aussi. Zéro question
gagnée, pour 522 Mo, 12 s de délai au pire et une dépendance à Ollama — une passe
a même attendu 320 s sur une question bloquée. Branché, mesuré, retiré.

**L'agent entièrement local (qwen3:8b).** Utile pour itérer à 0 $, mais ses
réponses ne sont pas comparables et il ne passe pas les tests notés. Retiré :
l'agent ne parle plus qu'à l'API, et le dépôt n'a plus rien à installer.

## 8. Ce qui reste à faire

Sortir la famille C des mains du modèle : brancher l'exécuteur du traducteur sur
`calculer`, qui sait déjà lire un filtre, et lui apprendre les cellules à deux
codes. Les questions à filtres passeraient de 0,00357 $ à environ 0,0002 $ et
deviendraient reproductibles — ce qu'elles ne sont pas aujourd'hui.
