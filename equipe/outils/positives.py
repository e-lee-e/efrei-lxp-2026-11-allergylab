"""Les dosages positifs au-dessus d'un seuil, pour une molécule.

Une case vide n'est pas un zéro : elle sort du dénominateur. Et le seuil
n'existe nulle part dans le fichier ni dans le dictionnaire officiel : c'est un
choix d'analyse, reçu en argument pour que la réponse puisse le citer.

Le calcul est dans `chiffres`, qui rend un dictionnaire ; `_positifs` le met en
phrases pour l'outil, et le routeur (equipe/routeur.py) réutilise les mêmes
nombres pour répondre sans appeler le modèle.
"""

import pandas as pd
from smolagents import tool

from equipe import cache
from equipe.outils.champs import NON_RENSEIGNE, texte
from kit.donnees import NB_CLINIQUES


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


def _positifs(tableau, allergene, seuil, groupe=""):
    """Le compte des positifs, et sa ventilation par groupe si on la demande."""
    calcul = chiffres(tableau, allergene, seuil, groupe)
    if calcul is None:
        return (
            f"colonne inconnue : {allergene!r}. Les colonnes de dosage commencent à la "
            f"seizième ; vérifie le nom exact de la molécule."
        )
    if calcul["n"] == 0:
        return f"{allergene} : aucun patient mesuré."

    entete = (
        f"{allergene} >= {seuil:g} : {calcul['positifs']} positifs sur {calcul['n']} "
        f"mesurés ({calcul['taux']:.1f} %)."
    )
    if not groupe:
        return entete
    if groupe not in tableau.columns:
        cliniques = ", ".join(map(str, tableau.columns[:NB_CLINIQUES]))
        return entete + f"\ngroupe inconnu : {groupe!r}. Les colonnes cliniques sont : {cliniques}."

    lignes = [
        f"{nom} : {touches} sur {total} ({100 * touches / total:.1f} %)"
        for nom, (touches, total) in calcul["par_groupe"].items()
    ]
    return entete + "\npar " + groupe + " :\n" + "\n".join(lignes)


@tool
def positifs(allergene: str, seuil: float, groupe: str = "") -> str:
    """Compte les patients dont le dosage d'une molécule atteint un seuil.

    Args:
        allergene: le nom exact de la colonne de dosage, par exemple "Bet_v_1".
        seuil: la valeur à partir de laquelle le dosage compte comme positif.
        groupe: colonne clinique facultative pour ventiler le compte, par exemple "Gender".

    Returns:
        Le nombre de positifs parmi les patients réellement mesurés, le
        pourcentage, et la ventilation par groupe si `groupe` est donné. Une case
        vide n'est jamais un zéro : elle sort du dénominateur.
    """
    return _positifs(cache.tableau(), allergene, seuil, groupe)
