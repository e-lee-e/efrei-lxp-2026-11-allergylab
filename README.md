# AllergyLab

Kit de démarrage de la semaine AllergyLab : on y construit un agent qui analyse un jeu de données de santé publié.

Le kit est un **harnais** : tout ce qui entoure le modèle et le rend utilisable, c'est-à-dire la boucle, les outils, la consigne, les garde-fous, les traces.

## Démarrer

Il faut deux outils sur la machine : git et uv. Clone le dépôt dans ton dossier personnel, hors d'un dossier synchronisé (OneDrive, iCloud), puis, depuis le dossier du dépôt :

```
uv run kit installer
uv run kit controle
uv run kit agent "Combien de lignes compte le tableau ?"
```

`uv run kit` seul affiche la liste des commandes. Chaque commande rend le code 0 quand tout va bien, 1 sinon. Tout passe par `uv run` : pas d'environnement virtuel à activer, pas de `pip`.

`installer` te demande la clé d'API que l'animateur t'a donnée : colle-la dans le terminal, rien ne s'affiche, c'est normal. Elle se range dans ton dossier personnel (`.allergylab/cle`), hors du dépôt : elle ne peut pas partir dans un commit. Pour la remplacer : `uv run kit cle`.

## Les données

`donnees/allergenchipchallenge-data-corrected-final-hdh-sfa.csv` est le jeu « Allergen Chip Challenge » publié par la Société Française d'Allergologie, DOI [10.60597/j5fe-g420](https://doi.org/10.60597/j5fe-g420), sous Licence Ouverte 2.0. Son dictionnaire officiel, `donnees/acc-dictionnaire-final.xls`, est livré tel que publié.

Ces deux fichiers sont dans le dépôt sans aucune modification, et on ne les modifie pas : `uv run kit controle` vérifie leur empreinte.

En Python :

```python
from kit.donnees import charger, colonnes

tableau = charger()      # le tableau complet, sans recodage ni filtrage
dictionnaire = colonnes()  # une ligne par colonne : bloc, lecture, types de puce
```

## Ce que le kit enregistre

Le kit garde une trace de chaque exécution, seul, sans que tu aies à y penser. Tout s'écrit dans le dossier `traces/` de ton dépôt. Le kit n'envoie ces traces nulle part : elles partent avec le reste de ton travail, à chaque `git push`.

**À chaque question posée à l'agent** (`uv run kit agent`), un fichier JSON dans `traces/appels/<jour>/`, nommé par l'heure (en temps universel, UTC) et un suffixe tiré au hasard. Il contient ces champs, et aucun autre :

| Champ | Contenu |
|---|---|
| `format` | la version du format de la trace |
| `horodatage` | la date et l'heure de l'appel, en UTC |
| `equipe` | l'identifiant de `equipe.toml` |
| `kit` | la version du kit |
| `etat` | l'empreinte de l'état de ton travail (voir plus bas) |
| `commit`, `modifie` | le commit git en cours, et s'il y a des modifications pas encore enregistrées ; vides hors d'un dépôt git |
| `moteur`, `modele` | ce qui fait tourner l'agent, et le modèle appelé |
| `question`, `reponse` | la question posée et la réponse rendue |
| `etapes` | les étapes de l'agent : le code qu'il a écrit, ses résultats tronqués |
| `jetons`, `cout_estime` | les jetons consommés et leur coût estimé |
| `duree_s` | la durée de l'appel, en secondes |
| `erreur` | l'erreur, s'il y en a eu une |

La trace s'écrit même quand l'appel échoue ou que tu l'interromps.

**À chaque état nouveau de ton travail**, une copie de `equipe/agent.py`, `equipe/consigne.md`, `equipe/outils/` et `equipe/questions/` dans `traces/etats/<empreinte>/`. L'empreinte résume le contenu de ces fichiers : tant qu'ils ne changent pas, rien n'est recopié. Chaque version de ton agent est ainsi gardée, que tu aies fait un commit ou non.

**Rien qui porte un nom.** Aucune trace ne contient ton nom d'utilisateur, le nom de ta machine, l'auteur des commits, ni rien qui te reconnaisse d'une exécution à l'autre. Avant toute écriture, le kit remplace le chemin de ton dossier personnel par `~`, ton nom d'utilisateur par `<utilisateur>`, et tout ce qui a la forme d'une clé d'API par `<clé>`.

Une limite : le texte libre. Ce que tu tapes dans une question, ce que tu écris dans ton code est recopié tel quel, et aucune machine ne sait y reconnaître un prénom. La règle est donc simple : on signe en équipe, jamais d'un prénom. L'historique git, lui, porte l'auteur de chaque commit ; il appartient aux membres de l'équipe et n'entre pas dans les traces.

**À quoi cela sert.** Pendant la semaine, à retrouver une erreur de l'agent avec ses étapes sans avoir pensé à faire une capture, et à comparer ton agent d'un jour à l'autre. Après la semaine, `traces/`, `JOURNAL.md` et `equipe.toml` sont collectés dans chaque dépôt d'équipe pour monter un dossier de valorisation de la semaine, sans nom d'étudiant. Ne supprime pas `traces/` : pousse-le avec le reste.

## Ce qu'un agent ouvert peut faire

L'agent livré dans `equipe/agent.py` est un `CodeAgent` de smolagents, **ouvert** : à chaque étape, le modèle écrit du code Python, et ce code s'exécute sur ton portable, avec tes droits, sans que personne l'ait relu.

- Ce code peut lire et écrire les fichiers de ton compte, et accéder au réseau. Ta clé d'API est un fichier de ton compte : un agent ouvert peut la lire comme n'importe quel autre. La vraie protection de la clé, c'est le plafond de dépense de ton équipe, et sa révocation.
- Deux lignes de `equipe/agent.py` ouvrent les données à l'agent, chacune signalée par un commentaire : celle qui autorise son code à importer pandas, celle qui lui passe le tableau complet. Tant qu'elles sont là, les outils de ton équipe ne sont qu'une option parmi d'autres pour lui.
- Retirer ces deux lignes **ferme** l'accès : l'agent écrit toujours du code, mais il n'atteint plus les données que par les outils de `equipe/outils/`. Fermer réduit ce qu'il peut faire ; ce n'est pas un bac à sable, et la documentation de smolagents le dit elle-même de son interpréteur.
- Un outil qui rend le tableau lui-même rouvre tout. Un outil rend une valeur simple : un nombre, un texte, une courte liste.
- Le bout de ce chemin : remplacer `CodeAgent` par `ToolCallingAgent`, qui n'exécute aucun code et n'appelle que les outils. Le kit a aussi un repli, `kit/boucle_maison.py`, une boucle d'outils qui n'exécute aucun code écrit par le modèle ; son mode d'emploi est en tête du fichier.
- La seule isolation réelle est de faire tourner l'agent sur une machine distante, pas sur ton portable.

Jusqu'où fermer est une décision de ton équipe, qu'elle justifie par ses scores.

Les variantes de notre agent (`ouvert`, `ferme`, `outils`) se choisissent par `ALLERGYLAB_VARIANTE`, voir l'en-tête de `equipe/agent.py`.

**Ce que coûte une question.** Chaque `uv run kit agent` affiche ses jetons et leur coût estimé. Le kit propose huit étapes au plus par question, sorties tronquées (`kit/reglages.toml`) ; notre agent n'en fait que cinq (`ETAPES_MAX` dans `equipe/agent.py`), parce que huit étapes ont coûté jusqu'à 0,008 $ une question. Ce sont des réglages, pas des verrous. La seule vraie limite est la cagnotte de ton équipe. Quand elle est épuisée, le kit affiche « cagnotte épuisée », écrit la trace et ne retente rien : va voir Adrien.

## Nos outils et leur sécurité

L'agent de l'équipe 2 n'offre que deux outils, dans `equipe/outils/` :

| Outil | Ce qu'il fait |
|---|---|
| `calculer` | compter, moyenne, médiane, pourcentage, valeurs manquantes, corrélation, avec un filtre et, si besoin, un calcul par groupe (`par`) |
| `chercher_colonne` | retrouver le nom exact d'une colonne à partir d'un mot |

Il y en a eu cinq. Chaque description d'outil est renvoyée au modèle à chaque étape, donc payée à chaque étape : `taux_par_groupe`, `taux_par_presence` et `positifs` ont été fusionnés dans `calculer` (commit 2c0ad37).

Ce qui touche à la sécurité, à relire en priorité dans `equipe/outils/_filtre.py` :

- Le filtre est un texte écrit par le modèle. Il est lu par deux expressions régulières (`CONDITION` et `DANS`), puis appliqué par des comparaisons pandas. Ni `eval`, ni `exec`, ni `query`. Ce qui n'a pas la forme « colonne comparaison valeur » ou « colonne dans valeur,valeur » est refusé.
- Le paramètre `par` passe par le même chemin, et il est limité à dix groupes (`MAX_GROUPES`).
- Un outil rend une phrase courte, jamais le tableau.
- Les tests `test_aucun_eval_exec_query`, `test_filtre_malveillant_refuse` et `test_les_deux_lignes_d_acces_restent_visibles` gardent ces règles.
- Fermer l'accès aux données réduit ce que l'agent peut faire ; ce n'est pas un bac à sable. Tant que `agent.py` est en variante `ouvert`, le code écrit par le modèle s'exécute sur le portable de la personne qui lance l'agent.

## Comment lire les données

Deux règles de lecture sont appliquées par l'outil, une fois pour toutes, pour que le modèle ne les réécrive pas à la main :

- une cellule peut porter plusieurs codes (« 1,3 ») : elle vaut les deux, et « 1 » ne se trouve pas dans « 10 » ;
- le code 9 veut dire « non renseigné » seulement dans les colonnes de `CODEES` (`_filtre.py`) ; dans `Age`, les mois et les dosages, 9 est une valeur.

Le détail des mesures est dans `equipe/TRAVAIL.md`, le déroulé jour par jour dans `JOURNAL.md`.

## Avant la remise

- Retirer les questions de contrôle et leurs valeurs attendues (`equipe/questions/`), et la règle d'abstention de `equipe/consigne.md` si l'animateur le demande : CLAUDE.md les interdit dans le dépôt du kit, l'équipe les garde ici comme échafaudage temporaire.
- Adapter ou supprimer `test_chiffre_attendu` (`equipe/tests/test_outils_agent.py`), qui lit ces valeurs.
- Décider avec l'animateur du sort de `traces/`, qui est versionné et contient des copies d'états.
- Relancer `uv run pytest -q` puis `uv run kit controle --hors-ligne` : les deux doivent rendre le code 0.
