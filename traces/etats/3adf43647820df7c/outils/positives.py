"""Les dosages positifs au-dessus d'un seuil, pour une molécule : le calcul du routeur.

Ce n'est plus un outil de l'agent : `calculer` fait la même chose avec le filtre
« Bet_v_1>=0.3 » (voir outils/calculer.py). Il reste ici parce que le routeur
(equipe/routeur.py) répond sans modèle avec ces nombres.

Une case vide n'est pas un zéro : elle sort du dénominateur. Et le seuil
n'existe nulle part dans le fichier ni dans le dictionnaire officiel : c'est un
choix d'analyse, reçu en argument pour que la réponse puisse le citer.
"""

import pandas as pd

from equipe.outils.champs import NON_RENSEIGNE, texte


def chiffres(tableau, allergene, seuil, groupe=""):
    """Les nombres derrière la réponse, ou None si la colonne n'existe pas.

    Rend {"n", "positifs", "taux", "par_groupe"} où par_groupe vaut
    {nom: (positifs, mesurés)}.
    """
    if allergene not in tableau.columns:
        return None

    valeurs = pd.to_numeric(tableau[allergene], errors="coerce")
    mesures = valeurs.notna()
    positifs = mesures & (valeurs >= seuil)
    n = int(mesures.sum())
    resultat = {
        "n": n,
        "positifs": int(positifs.sum()),
        "taux": 100 * positifs.sum() / n if n else 0.0,
        "par_groupe": {},
    }

    if groupe and groupe in tableau.columns:
        noms = tableau[groupe].map(texte)
        utilisables = mesures & noms.notna() & (noms != NON_RENSEIGNE)
        for nom in sorted(noms[utilisables].unique()):
            du_groupe = utilisables & (noms == nom)
            resultat["par_groupe"][nom] = (int((du_groupe & positifs).sum()), int(du_groupe.sum()))
    return resultat
