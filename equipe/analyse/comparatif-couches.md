# Comparatif des couches de l'agent

Tableau reconstitué depuis `equipe/mesures/` et `traces/evaluations/`, rien d'estimé à
la main. Modèle de développement (Haiku 5.5). Les « justes » sont comptés contre les
valeurs attendues des questions de l'équipe, qui sont un échafaudage temporaire (voir
`equipe/TRAVAIL.md`, section 8).

## Passe de 75 questions (`lot-2-20261117T223917.json`, soir du 17 novembre)

| Couche qui a répondu | Questions | Justes | Coût | Temps moyen |
|---|---|---|---|---|
| portier hors sujet | 13 | 13 | 0 $ | 0 s |
| routeur | 6 | 6 | 0 $ | 0 s |
| cache | 8 | 7 | 0 $ | 0 s |
| traducteur | 29 | 29 | 0,0058 $ | 1,3 s |
| agent complet (`CodeAgent`) | 19 | 17 | 0,0459 $ | 9,6 s |
| **Total** | **75** | **72** | **0,0517 $** | |

- 56 questions sur 75 (75 %) n'ont pas eu besoin de l'agent complet.
- L'agent complet répond à 25 % des questions et pèse 89 % du coût (0,0459 sur 0,0517 $).
- Les trois erreurs (D02, D06, D09) sont des réponses données à des questions qui
  attendaient une abstention : unité imposée, ou molécule présentée comme un aliment.
  Elles ont été corrigées le 18 novembre (voir `equipe/RECAP-2026-11-18.md`, section 2).

## Coût d'une question selon la couche

| Couche | Coût par question | Reproductible |
|---|---|---|
| portier, routeur, cache | 0 $ | oui |
| traducteur | 0,0002 à 0,0003 $ | oui, le calcul est fait par le code |
| agent complet | 0,001 à 0,0068 $ (3 à 24 s) | non, le modèle écrit du code à chaque fois |

## Campagne du 18 novembre, sans cache, sur le code corrigé

| Terrain | Résultat | Coût par question | Temps |
|---|---|---|---|
| Batterie de référence, 56 questions | justesse 26/26, abstentions 30/30 | 0,000457 $ | 1,9 s |
| Batterie fraîche, 17 questions | 17/17 | 0,000775 $ | 3,0 s |
| Quatre fichiers étrangers, 10 questions | 9/10, une abstention | 0,0002 à 0,005 $ | 2 à 4 s |

La passe Sonnet du 18 novembre a porté sur 6 questions (4 justes sur 4, 2 abstentions
fondées sur 2) : trop peu pour comparer les deux modèles.

## Ce que ce tableau ne dit pas

Les trois variantes de l'agent (`ouvert`, `ferme`, `outils`, voir `equipe/agent.py`)
n'ont pas de scores comparés dans le dépôt : la variante ne figure pas dans les traces
d'évaluation, et les passes ci-dessus ont tourné avec la variante livrée (`ouvert`).
Pour les comparer :

    ALLERGYLAB_VARIANTE=ferme ALLERGYLAB_SANS_CACHE=1 ALLERGYLAB_RACCOURCIS=0 uv run kit evaluer <batterie>

puis la même commande avec `outils` et `ouvert`, et noter chaque fois la justesse, l'abstention
et la frugalité. `ALLERGYLAB_RACCOURCIS=0` coupe les couches locales : sans lui, la
comparaison mesure le routeur, pas la variante. Ces passes appellent le modèle ; leur nombre
se décide avec l'équipe.
