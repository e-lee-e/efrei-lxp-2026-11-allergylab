"""Le tableau des patients, chargé une seule fois pour tous les outils.

Ce n'est pas un outil : le nom commence par « _ » pour que personne ne le
branche sur l'agent. Les outils l'appellent pour calculer, et ne rendent
jamais le tableau lui-même, seulement des valeurs simples.
"""

def tableau():
    """Le tableau des patients, tel que le cache le connaît.

    Passer par equipe.cache.tableau() et non charger() : c'est là que vivent le
    fichier choisi dans la fenêtre et la table qu'une évaluation met à la place
    du fichier publié. Sans ça, les outils calculaient sur le vrai fichier
    pendant que le modèle en recevait un autre — mesuré sur une table inventée
    sans la colonne Sensitization, où l'agent répondait 80,9 %.
    """
    from equipe.cache import tableau as tableau_du_cache

    return tableau_du_cache()
