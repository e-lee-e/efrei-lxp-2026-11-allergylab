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

## Cinq pièges qui coûtent une mesure

1. **Le cache fausse toute mesure** : une question rejouée sort à 0 jeton. Utiliser
   `ALLERGYLAB_SANS_CACHE=1` avant de conclure quoi que ce soit.
2. **Un outil non routé est une taxe** : mesuré à +50 % de coût pour la même
   réponse, quand le modèle réécrit du pandas au lieu d'appeler l'outil.
3. **Une étape qui n'est pas du code est perdue** : smolagents attend du Python
   exécutable ; un appel d'outil écrit en JSON ou en prose déclenche « code
   parsing » et brûle une étape entière (~6 000 jetons). La consigne doit dire
   qu'un appel d'outil s'écrit dans un bloc de code, suivi d'un `print`.
4. **`uv run pytest` voit maintenant `equipe/tests`** : la fusion de a/agent-outils
   a étendu `testpaths` à `["kit/tests", "equipe/tests"]`. Les deux commandes
   marchent ; celle qui ne lance que l'équipe reste `uv run pytest equipe/tests -q`.
5. **`kit/` est figé** : `controle` vérifie son empreinte à partir du lot 2.
   Toute idée d'optimisation dans `kit/` se traduit en `equipe/` ou ne se fait pas.

## Ce qu'on a abandonné, et pourquoi

**Le reformulateur local (qwen3:0.6b, 522 Mo).** Un petit modèle Ollama réécrivait
la question dans une forme connue du routeur. Sur les 40 questions de
`equipe/questions/lot-gpt.toml` : le routeur seul en route 8, le routeur avec le
modèle en route 8 aussi. **Zéro question gagnée**, pour 522 Mo, 12 s de délai au
pire et une dépendance à un serveur local. Une passe a même attendu 320 s sur une
question bloquée. Il a été branché, mesuré, puis retiré ; `modele_local.py` et
`reformulateur.py` ont été supprimés.

La conclusion n'est pas « un petit modèle ne sert à rien », mais « sur ces
quarante-là, il ne servait à rien ». Le jour où une batterie montre des tournures
qu'il rattrape, la mesure se refait en une heure.

**L'agent entièrement local (qwen3:8b).** Utile pour itérer à 0 $, mais ses
réponses ne sont pas comparables à celles d'Anthropic et il ne passe pas les tests
notés. Retiré aussi : l'agent ne parle plus qu'à l'API, ce qui rend le dépôt
transportable — rien à installer, rien à télécharger.
