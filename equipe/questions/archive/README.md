# Archive des premières batteries

Ces trois fichiers datent d'avant le format du harnais. Ils déclarent `famille` et
`attend` (« reponse » ou « abstention »), deux clés que `kit evaluer` refuse : il
n'accepte que `id`, `texte`, `type`, `attendu`, `tolerance`, et `type` vaut
`nombre`, `choix` ou `sans-reponse`.

Ils ne sont pas convertibles en l'état : dire `type = "nombre"` exige une valeur
attendue, et la règle 4 du projet interdit de stocker une réponse calculée sur le
fichier réel dans le dépôt. Les garder ici conserve les 139 questions comme
journal de ce qu'on a exploré.

Le harnais lit `equipe/questions/*.toml` sans descendre dans les sous-dossiers :
ces fichiers ne le bloquent donc pas. Les lots utilisables sont au-dessus :
`batterie-kit.toml`, `lot01-base.toml`, `lot02-clinique.toml`.
