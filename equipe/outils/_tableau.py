"""Le tableau des patients, chargé une seule fois pour tous les outils.

Ce n'est pas un outil : le nom commence par « _ » pour que personne ne le
branche sur l'agent. Les outils l'appellent pour calculer, et ne rendent
jamais le tableau lui-même, seulement des valeurs simples.
"""

from functools import cache

from kit.donnees import charger


@cache  # la lecture du fichier prend un moment : une seule fois par exécution
def tableau():
    return charger()
