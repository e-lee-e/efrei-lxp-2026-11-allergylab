# Ce que le kit fait vraiment, vérifié dans le code

Notes de lecture, pas de la documentation officielle. Chaque ligne a été
vérifiée dans `kit/` ou dans les traces, pour éviter les fausses alertes du
genre « les données contredisent le dictionnaire ».

## Carte du kit

| Fichier | Rôle | Ce qu'il faut savoir |
|---|---|---|
| `kit/donnees.py` | charger le CSV | séparateur `;`, UTF-8 avec BOM, **virgule décimale** dans le bloc dosage ; une colonne clinique qui contient une virgule ou une lettre reste en texte ; `NB_CLINIQUES = 15` |
| `kit/controle.py` | `kit controle` | 9 vérifications ; `--hors-ligne` saute la clé et l'appel ; identifiant d'équipe valide = `accueil` ou `equipe-1..9` |
| `kit/modele.py` | seul module qui parle au modèle | `LiteLLMModel("anthropic/…")` : **aucun modèle local possible** ; `en_cours = "developpement"` (haiku) ou `"officiel"` (sonnet, 20× le prix) |
| `kit/question.py` | `kit agent` | appelle `equipe.agent.repondre`, valide le contrat, écrit la trace ; le bilan n'affiche les jetons que si `journal["modele"]` est rempli |
| `kit/reponse.py` | contrat | 3 champs exactement ; **justification ≤ 3 phrases**, comptées sur `.` `!` `?` `…` ; une 4e phrase = « réponse illisible », verdict perdu |
| `kit/traces.py` | traces | 16 champs fermés ; anonymisation du dossier personnel, du nom d'utilisateur et des clés ; `traces/` n'entre pas dans le calcul de `modifie` |
| `kit/boucle_maison.py` | repli | boucle d'outils maison, **n'exécute aucun code** ; mêmes outils, même contrat ; s'active en changeant un import ; ignore `additional_args` |
| `kit/empreintes.toml` | empreintes | SHA-256 des deux fichiers de `donnees/`, plus la forme attendue (4271 × 256) |

## Le dictionnaire des colonnes (`kit/colonnes.csv`)

L'ordre des colonnes de puce est `puce_ALEX`, `puce_ISAC_V1`, `puce_ISAC_V2`.
Une erreur de lecture ici produit une fausse alerte : `Act_d_8,dosage,nombre,faux,vrai,vrai`
veut dire ALEX = faux, ISAC v1 = vrai, ISAC v2 = vrai. Vérifié sur les données :
`Act_d_8` a 0 valeur chez les 1 139 patients ALEX, 2 351 chez ISAC_V1, 781 chez ISAC_V2.

Un vide dans une colonne de dosage veut dire « non mesuré », jamais zéro. Le
dénominateur d'un outil, c'est donc le nombre de patients **mesurés**, pas 4 271.

## Où part l'argent (mesuré sur `traces/appels/`)

| Étapes | Jetons entrée | Coût mesuré | Durée |
|---|---|---|---|
| 2 | 11 268 | 0,001513 $ | 9,1 s |
| 3 | 18 479 | 0,003036 $ | 13,4 s |
| 4 | 26 438 | 0,004058 $ | 15,7 s |

Environ 5 000 jetons au premier appel, puis ~7 000 par étape, parce que tout le
contexte est renvoyé à chaque fois. Coût = (entrée × 0,10 + sortie × 0,50) / 1e6.

Poids mesurés au tokenizer : la consigne fait **1 249 jetons** (24 % du premier
appel) et les deux outils **375 jetons** de description, repayés à chaque étape.
C'est pour ça qu'un outil non routé coûte plus qu'il ne rapporte.

## Quatre pièges qui coûtent une mesure

1. **Le cache fausse toute mesure** : une question rejouée sort à 0 jeton. Utiliser
   `ALLERGYLAB_SANS_CACHE=1` avant de conclure quoi que ce soit.
2. **Un outil non routé est une taxe** : mesuré à +50 % de coût pour la même
   réponse, quand le modèle réécrit du pandas au lieu d'appeler l'outil.
3. **`uv run pytest` ne voit pas `equipe/tests`** : `pyproject.toml` fixe
   `testpaths = ["kit/tests"]`. La commande est `uv run pytest equipe/tests -q`.
   Le fichier `pyproject.toml` n'est pas à nous (Adrien le pousse) : on n'y touche pas.
4. **`kit/` est figé** : `controle` vérifie son empreinte à partir du lot 2.
   Toute idée d'optimisation dans `kit/` se traduit en `equipe/` ou ne se fait pas.
